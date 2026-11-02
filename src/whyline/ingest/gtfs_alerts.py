"""CLI to snapshot RTD's GTFS-Realtime service alerts.

Runs from the realtime-load job every 15 minutes. Each snapshot writes two files under
raw/rtd_gtfsrt_alerts/snapshot_at=<UTC minute>/: alerts.csv.gz (one row per alert and informed
entity) and alert_periods.csv.gz (one row per alert and active period), so an alert with many
daily periods and many stops doesn't multiply out.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from google.transit import gtfs_realtime_pb2

from whyline.ingest import io
from whyline.ingest.gtfs_realtime import (
    _ensure_directory_target,
    _join_path,
    _write_bytes,
    fetch_feed,
    serialize_dataframe,
)

DEFAULT_ALERTS_URL = "https://open-data.rtd-denver.com/files/gtfs-rt/rtd/Alerts.pb"

# Column order must equal the loader registry (raw_gtfsrt_alerts, raw_gtfsrt_alert_periods).
ALERT_COLUMNS = [
    "feed_ts_utc",
    "alert_id",
    "cause",
    "effect",
    "header_text",
    "description_text",
    "url",
    "agency_id",
    "route_id",
    "route_type",
    "direction_id",
    "stop_id",
    "trip_id",
]
PERIOD_COLUMNS = ["feed_ts_utc", "alert_id", "active_start_utc", "active_end_utc"]

LOGGER = io.get_logger(__name__)


def _iso(epoch: int) -> str | None:
    """GTFS-RT uses 0 for an open start or end."""
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(translated: Any) -> str | None:
    """English translation if present, else the first one."""
    translations = list(translated.translation)
    for t in translations:
        if t.language in ("en", "en-US", ""):
            return t.text
    return translations[0].text if translations else None


def parse_alerts(payload: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    feed_ts = _iso(feed.header.timestamp)
    alerts, periods = [], []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert
        base = [
            feed_ts,
            entity.id,
            gtfs_realtime_pb2.Alert.Cause.Name(a.cause) if a.HasField("cause") else None,
            gtfs_realtime_pb2.Alert.Effect.Name(a.effect) if a.HasField("effect") else None,
            _text(a.header_text),
            _text(a.description_text),
            _text(a.url),
        ]
        for e in a.informed_entity or [None]:
            if e is None:
                alerts.append(base + [None] * 6)
                continue
            alerts.append(
                base
                + [
                    e.agency_id or None,
                    e.route_id or None,
                    e.route_type if e.HasField("route_type") else None,
                    e.direction_id if e.HasField("direction_id") else None,
                    e.stop_id or None,
                    (e.trip.trip_id or None) if e.HasField("trip") else None,
                ]
            )
        for p in a.active_period:
            periods.append([feed_ts, entity.id, _iso(p.start), _iso(p.end)])
    alert_df = pd.DataFrame(alerts, columns=ALERT_COLUMNS)
    for col in ("route_type", "direction_id"):
        alert_df[col] = alert_df[col].astype("Int64")
    return alert_df, pd.DataFrame(periods, columns=PERIOD_COLUMNS)


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
    snapshot_dir = _join_path(root, "rtd_gtfsrt_alerts", f"snapshot_at={label}")
    if io.exists(_join_path(snapshot_dir, "manifest.json")):
        LOGGER.info("Skipping alerts snapshot %s; manifest already present.", label)
        return 0

    payload, error = fetch_feed(args.url, args.timeout_sec)
    if payload is None:
        LOGGER.warning("ALERTS_FETCH_FAILED %s", error)
        return 1
    alerts, periods = parse_alerts(payload)

    files: dict[str, dict[str, Any]] = {}
    for name, df in (("alerts.csv.gz", alerts), ("alert_periods.csv.gz", periods)):
        data = serialize_dataframe(df)
        path = _join_path(snapshot_dir, name)
        _write_bytes(path, data, content_type="application/gzip")
        files[name] = {
            "path": str(path),
            "row_count": int(len(df)),
            "bytes": io.sizeof_bytes(data),
            "hash_md5": io.hash_bytes_md5(data),
        }
    io.write_manifest(
        _ensure_directory_target(snapshot_dir),
        {
            "source": args.url,
            "snapshot_at": label,
            "feed_ts_utc": alerts["feed_ts_utc"].iloc[0] if len(alerts) else None,
            "n_alerts": int(alerts["alert_id"].nunique()),
            "files": files,
            "written_at_utc": io.utc_now_iso(),
            "duration_sec": round(time.time() - started, 2),
        },
    )
    LOGGER.info(
        "Alerts snapshot %s: %d alerts, %d entity rows, %d periods.",
        label,
        alerts["alert_id"].nunique(),
        len(alerts),
        len(periods),
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot RTD GTFS-Realtime service alerts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--url", default=DEFAULT_ALERTS_URL, help="Alerts GTFS-RT feed URL.")
    parser.add_argument("--timeout-sec", type=int, default=15)
    parser.add_argument("--now-utc", help="Override 'now' in ISO-8601 (for testing).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
