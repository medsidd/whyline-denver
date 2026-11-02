"""CLI to snapshot Veo's Denver GBFS vehicle availability.

Veo has been Denver's only scooter and e-bike operator since May 2026. Runs from the
realtime-load job every 15 minutes and writes raw/gbfs_veo/snapshot_at=<UTC minute>/vehicles.csv.gz.
bike_id and rental URIs are dropped: GBFS rotates the ID for privacy, and the URIs carry a
persistent vehicle number. Times stay in UTC; the feed's system timezone says America/Chicago.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io
from whyline.ingest.gtfs_realtime import (
    _ensure_directory_target,
    _join_path,
    _write_bytes,
    fetch_feed,
    serialize_dataframe,
)
from whyline.ingest.rt_engine import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

DEFAULT_GBFS_URL = "https://cluster-prod.veoride.com/api/shares/name/den/gbfs"
MIN_VEHICLES = 1000  # Veo lists about 8,000; far fewer means a broken feed, not an empty city
MIN_IN_BOX = 0.95

# Column order must equal the loader registry (raw_gbfs_veo_vehicles).
VEHICLE_COLUMNS = [
    "snapshot_ts_utc",
    "vehicle_type_id",
    "form_factor",
    "propulsion",
    "lat",
    "lon",
    "is_reserved",
    "is_disabled",
    "current_range_m",
]

LOGGER = io.get_logger(__name__)


def parse_vehicles(free_bike_status: dict, vehicle_types: dict) -> pd.DataFrame:
    types = {
        t["vehicle_type_id"]: (t.get("form_factor"), t.get("propulsion_type"))
        for t in vehicle_types.get("data", {}).get("vehicle_types", [])
    }
    ts = datetime.fromtimestamp(free_bike_status["last_updated"], UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = []
    for b in free_bike_status.get("data", {}).get("bikes", []):
        form, propulsion = types.get(b.get("vehicle_type_id"), (None, None))
        rows.append(
            [
                ts,
                b.get("vehicle_type_id"),
                form,
                propulsion,
                b.get("lat"),
                b.get("lon"),
                bool(b.get("is_reserved")),
                bool(b.get("is_disabled")),
                b.get("current_range_meters"),
            ]
        )
    df = pd.DataFrame(rows, columns=VEHICLE_COLUMNS)
    df["current_range_m"] = df["current_range_m"].round().astype("Int64")
    for col in ("is_reserved", "is_disabled"):
        df[col] = df[col].map({True: "true", False: "false"})
    return df


def in_box_share(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    inside = df.lon.between(LON_MIN, LON_MAX) & df.lat.between(LAT_MIN, LAT_MAX)
    return float(inside.mean())


def _get_json(url: str, timeout_sec: int) -> tuple[dict | None, str | None]:
    payload, error = fetch_feed(url, timeout_sec)
    if payload is None:
        return None, error
    try:
        return json.loads(payload), None
    except ValueError as exc:
        return None, f"invalid JSON: {exc}"


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    started = time.time()
    now = datetime.fromisoformat(args.now_utc) if args.now_utc else datetime.now(UTC)
    label = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")
    if args.mode == "local":
        root: Any = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"
    snapshot_dir = _join_path(root, "gbfs_veo", f"snapshot_at={label}")
    if io.exists(_join_path(snapshot_dir, "manifest.json")):
        LOGGER.info("Skipping Veo snapshot %s; manifest already present.", label)
        return 0

    base = args.url.rstrip("/")
    status, error = _get_json(f"{base}/free_bike_status", args.timeout_sec)
    types, types_error = _get_json(f"{base}/vehicle_types", args.timeout_sec)
    if status is None or types is None:
        LOGGER.warning("VEO_FETCH_FAILED %s", error or types_error)
        return 1
    df = parse_vehicles(status, types)
    share = in_box_share(df)
    if len(df) < MIN_VEHICLES or share < MIN_IN_BOX:
        LOGGER.warning("VEO_FEED_SUSPECT vehicles=%d in_box=%.3f; not written", len(df), share)
        return 1

    data = serialize_dataframe(df)
    path = _join_path(snapshot_dir, "vehicles.csv.gz")
    _write_bytes(path, data, content_type="application/gzip")
    io.write_manifest(
        _ensure_directory_target(snapshot_dir),
        {
            "source": base,
            "snapshot_at": label,
            "snapshot_ts_utc": df["snapshot_ts_utc"].iloc[0],
            "files": {
                "vehicles.csv.gz": {
                    "path": str(path),
                    "row_count": int(len(df)),
                    "bytes": io.sizeof_bytes(data),
                    "hash_md5": io.hash_bytes_md5(data),
                }
            },
            "quality": {
                "in_box_share": round(share, 4),
                "n_unknown_type": int(df.form_factor.isna().sum()),
            },
            "written_at_utc": io.utc_now_iso(),
            "duration_sec": round(time.time() - started, 2),
        },
    )
    LOGGER.info("Veo snapshot %s: %d vehicles.", label, len(df))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot Veo's Denver GBFS vehicles.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--url", default=DEFAULT_GBFS_URL, help="Veo GBFS root URL.")
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--now-utc", help="Override 'now' in ISO-8601 (for testing).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
