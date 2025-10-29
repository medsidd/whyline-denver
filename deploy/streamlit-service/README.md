# Streamlit Service Deployment Notes

The Streamlit app runs on Cloud Run and mounts the DuckDB warehouse from Cloud Storage
so the UI can swap between DuckDB and BigQuery engines without extra infrastructure.

## Container Layout

- **Entrypoint**: `/start.sh` launches Streamlit (bound to `127.0.0.1:8501` with `--server.baseUrlPath=/app`) and then runs nginx in the foreground.
- **Reverse proxy**: `deploy/streamlit-service/nginx.conf` issues `301 / → /app`, serves static placeholders from `/usr/share/nginx/html` (`/docs`, `/data`, `/favicon.ico`, `/assets/*`), and proxies `/app/*` to Streamlit with websocket support.
- **Placeholders**: `app/placeholders/` contains HTML stubs so `/docs` and `/data` exist ahead of future docs/downloads. The root placeholder auto-redirects to `/app/`.
- **Safari favicon**: Streamlit injects a `mask-icon` snippet so pinned tabs show the WhyLine mark; nginx also exposes `/favicon.ico` and `/assets/whylinedenver-logo.svg` for the landing pages.

## Local QA

If `GOOGLE_APPLICATION_CREDENTIALS` is set, the startup script will download
`gs://whylinedenver-raw/marts/duckdb/warehouse.duckdb` and `sync_state.json` for
you. Without credentials, mount a local `data/` folder containing those files.
Mounting `.env` into `/app/.env` (done automatically by `make streamlit-run`) lets
the app pick up LLM configuration such as `GEMINI_API_KEY` via python-dotenv.

When running on Cloud Run, prefer mounting the bucket via GCS Fuse (e.g. at
`/mnt/gcs`). If `/mnt/gcs/marts/duckdb/warehouse.duckdb` exists, the startup
script symlinks it into `/app/data/warehouse.duckdb` and skips the download
step; the parquet cache is exposed via `/app/data/marts` so DuckDB views continue
to work. Override `DUCKDB_PARQUET_ROOT` if you mount to a different directory.

```bash
# If you want BigQuery access, export a service account path first
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json"
make streamlit-run
open http://localhost:8080/
```

Expected results:
- `GET /` responds `301` with `Location: /app/`.
- `GET /app/` renders the Streamlit UI with assets loading under the subpath.
- `GET /docs/` and `GET /data/` return the placeholder HTML.
- `GET /favicon.ico` returns the site icon (Safari pinned tabs read the mask SVG).

Stop the container with `Ctrl+C`; the Makefile target removes the container automatically.

## DuckDB Artifact Location

- **Bucket:** `gs://whylinedenver-raw`
- **Object:** `marts/duckdb/warehouse.duckdb`

The nightly `nightly-duckdb` GitHub Actions workflow refreshes mart exports, rebuilds
`warehouse.duckdb`, and uploads the artifact to the path above. Each run overwrites the
single blob so Cloud Run always sees the latest snapshot when the GCS Fuse volume mounts
`/mnt/duckdb/warehouse.duckdb`.

## Required IAM Roles

Run the Streamlit service with a dedicated service account (e.g. `streamlit-app@`), or
reuse an existing one, with the following project-level roles:

- `roles/storage.objectViewer` on `whylinedenver-raw` so the container can read the
  DuckDB blob via the Cloud Storage mount.
- `roles/bigquery.jobUser` to submit query jobs when the BigQuery engine is selected.
- `roles/bigquery.dataViewer` to read datasets referenced by the app.

Grant these roles before deploying the Cloud Run service to avoid cold-start failures
when the app attempts to read the warehouse or issue BigQuery queries.
