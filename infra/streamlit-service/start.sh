#!/usr/bin/env bash
set -euo pipefail

STREAMLIT_CMD=(
  streamlit run app/streamlit_app.py \
        --server.baseUrlPath=/app \
    --server.port=8501 \
        --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.headless=true
)

cleanup() {
  for pid in "${ST_PID:-}" "${NGINX_PID:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" || true
    fi
  done
}
trap cleanup EXIT INT TERM

export GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-}}

GCS_MOUNT_ROOT=${GCS_MOUNT_ROOT:-/mnt/gcs}
MOUNTED_DUCKDB="${GCS_MOUNT_ROOT}/marts/duckdb/warehouse.duckdb"
MOUNTED_SYNC_STATE="${GCS_MOUNT_ROOT}/state/sync_state.json"
MOUNTED_MARTS_DIR="${GCS_MOUNT_ROOT}/marts"

ensure_data_dirs() {
  mkdir -p /app/data
  mkdir -p /app/data/marts
  
  # If GCS is mounted, create symlink to mounted marts for fallback
  if [ -d "$MOUNTED_MARTS_DIR" ]; then
    # Don't overwrite /app/data/marts if it already has downloaded content
    if [ ! -d "/app/data/marts_gcs" ]; then
      ln -sfn "$MOUNTED_MARTS_DIR" /app/data/marts_gcs
      echo "Created symlink: /app/data/marts_gcs -> $MOUNTED_MARTS_DIR"
    fi
  fi
}

ensure_data_dirs

# Create symlinks for DuckDB and sync_state if they exist on GCS mount
if [ -f "$MOUNTED_DUCKDB" ]; then
  ln -sfn "$MOUNTED_DUCKDB" /app/data/warehouse.duckdb.mounted
  echo "Created symlink: /app/data/warehouse.duckdb.mounted -> $MOUNTED_DUCKDB"
fi

if [ -f "$MOUNTED_SYNC_STATE" ]; then
  ln -sfn "$MOUNTED_SYNC_STATE" /app/data/sync_state.json.mounted
  echo "Created symlink: /app/data/sync_state.json.mounted -> $MOUNTED_SYNC_STATE"
fi

NEED_DUCKDB_DOWNLOAD=1
NEED_SYNC_DOWNLOAD=1
[ -f /app/data/warehouse.duckdb ] && NEED_DUCKDB_DOWNLOAD=0
[ -f /app/data/sync_state.json ] && NEED_SYNC_DOWNLOAD=0

echo "Startup checks: NEED_DUCKDB_DOWNLOAD=$NEED_DUCKDB_DOWNLOAD, NEED_SYNC_DOWNLOAD=$NEED_SYNC_DOWNLOAD"

if [ "$NEED_DUCKDB_DOWNLOAD" -eq 1 ] || [ "$NEED_SYNC_DOWNLOAD" -eq 1 ]; then
  echo "Downloading missing artifacts from GCS..."
  python - <<'PY' || true
import os
import sys
from pathlib import Path

from google.cloud import storage

project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID")

targets = []
if os.getenv("GCS_BUCKET") and os.getenv("DUCKDB_GCS_BLOB") and not Path("/app/data/warehouse.duckdb").exists():
    targets.append((os.getenv("GCS_BUCKET"), os.getenv("DUCKDB_GCS_BLOB"), Path("/app/data/warehouse.duckdb"), "DuckDB artifact"))
if os.getenv("SYNC_STATE_GCS_BUCKET") and os.getenv("SYNC_STATE_GCS_BLOB") and not Path("/app/data/sync_state.json").exists():
    targets.append((os.getenv("SYNC_STATE_GCS_BUCKET"), os.getenv("SYNC_STATE_GCS_BLOB"), Path("/app/data/sync_state.json"), "sync_state"))

if not targets:
    sys.exit(0)

try:
    client = storage.Client(project=project) if project else storage.Client()
except Exception as exc:  # pragma: no cover
    print(f"WARNING: Unable to initialize Google Cloud Storage client: {exc}", file=sys.stderr)
    sys.exit(0)

for bucket_name, blob_name, local_path, label in targets:
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(local_path)
        print(f"Downloaded {label} to {local_path}")
    except Exception as exc:  # pragma: no cover - network / missing blob
        print(
            f"WARNING: Failed to download {label} from gs://{bucket_name}/{blob_name}: {exc}",
            file=sys.stderr,
        )
PY
fi

# Download parquet marts when not mounted and directory is empty
MARTS_EXIST=$(ls -A /app/data/marts 2>/dev/null | wc -l)
echo "Checking parquet marts: files_count=$MARTS_EXIST"

if [ "$MARTS_EXIST" -eq 0 ]; then
  echo "Downloading parquet marts from GCS..."
  python - <<'PY' || true
import os
import sys
from pathlib import Path

from google.cloud import storage

from whyline.sync.constants import ALLOWLISTED_MARTS

project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID")
bucket_name = os.getenv("GCS_BUCKET")
cache_root = Path("/app/data/marts")
cache_root.mkdir(parents=True, exist_ok=True)

if not bucket_name:
    sys.exit(0)

try:
    client = storage.Client(project=project) if project else storage.Client()
except Exception as exc:  # pragma: no cover
    print(f"WARNING: Unable to init storage client for parquet download: {exc}", file=sys.stderr)
    sys.exit(0)

for mart in ALLOWLISTED_MARTS:
    prefix = f"marts/{mart}/"
    dest_root = cache_root / mart
    existing = any(dest_root.glob("run_date=*/**/*"))
    if existing:
        continue
    try:
        blobs = client.list_blobs(bucket_name, prefix=prefix)
    except Exception as exc:  # pragma: no cover
        print(f"WARNING: Failed to list parquet for {mart}: {exc}", file=sys.stderr)
        continue

    downloaded = 0
    for blob in blobs:
        name = blob.name
        if not name or name.endswith("/"):
            continue
        relative = name.split("marts/", 1)[-1]
        if relative.startswith("/") or "../" in relative or relative == "..":
            print(f"WARNING: Skipping suspicious parquet object name: {name}", file=sys.stderr)
            continue
        local_path = (cache_root / relative).resolve()
        try:
            local_path.relative_to(cache_root.resolve())
        except ValueError:
            print(f"WARNING: Skipping parquet outside cache root: {name}", file=sys.stderr)
            continue
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            blob.download_to_filename(local_path)
            downloaded += 1
        except Exception as exc:  # pragma: no cover
            print(f"WARNING: Failed to download {name}: {exc}", file=sys.stderr)
    if downloaded:
        print(f"Downloaded {downloaded} parquet files for {mart}")
    else:
        print(f"No parquet files downloaded for {mart} (already cached or empty)")
PY
fi

# 1) start streamlit (background)
"${STREAMLIT_CMD[@]}" &
ST_PID=$!

# 2) Wait for Streamlit to start accepting connections before starting nginx
python - <<'PY' || true
import socket
import sys
import time

address = ("127.0.0.1", 8501)
start = time.time()
deadline = start + 30  # seconds

while time.time() < deadline:
    try:
        with socket.create_connection(address, timeout=1):
            break
    except OSError:
        time.sleep(0.5)
else:
    print("WARNING: Streamlit did not become ready within 30 seconds", file=sys.stderr)
PY

# 3) launch nginx (background)
nginx -g 'daemon off;' &
NGINX_PID=$!

# 4) wait for either process to exit, then clean up
wait -n "${ST_PID}" "${NGINX_PID}"
STATUS=$?
cleanup
wait || true
exit "${STATUS}"
