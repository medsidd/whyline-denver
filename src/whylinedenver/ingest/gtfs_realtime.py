"""CLI to ingest RTD GTFS-Realtime Trip Updates and Vehicle Positions feeds."""

from __future__ import annotations

import argparse
import gzip
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Union

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2

from whylinedenver.ingest import common

DEFAULT_TRIP_UPDATES_URL = "https://www.rtd-denver.com/files/gtfs-rt/TripUpdate.pb"
DEFAULT_VEHICLE_POSITIONS_URL = "https://www.rtd-denver.com/files/gtfs-rt/VehiclePosition.pb"

DENVER_LON_MIN = -105.5
DENVER_LON_MAX = -104.4
DENVER_LAT_MIN = 39.4
DENVER_LAT_MAX = 40.2

TRIP_UPDATES_COLUMNS = [
    "feed_ts_utc",
    "entity_id",
    "trip_id",
    "route_id",
    "stop_id",
    "stop_sequence",
    "arrival_delay_sec",
    "departure_delay_sec",
    "schedule_relationship",
    "event_ts_utc",
    "start_date",
    "start_time",
]

VEHICLE_POSITIONS_COLUMNS = [
    "feed_ts_utc",
    "entity_id",
    "trip_id",
    "route_id",
    "vehicle_id",
    "vehicle_label",
    "lon",
    "lat",
    "bearing",
    "speed_mps",
    "event_ts_utc",
]

LOGGER = common.get_logger(__name__)
PathLike = Union[str, Path]


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    if args.snapshots <= 0:
        raise SystemExit("--snapshots must be >= 1")
    if args.interval_sec < 0:
        raise SystemExit("--interval-sec must be >= 0")

    base_time = determine_base_time(args.now_utc)
    route_filter = parse_route_filter(args.route_filter)

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    captured = 0
    for index in range(args.snapshots):
        tick_start = time.time()
        feed_time = (base_time + timedelta(seconds=args.interval_sec * index)).replace(
            second=0, microsecond=0
        )
        feed_ts_iso = feed_time.isoformat().replace("+00:00", "Z")
        snapshot_label = feed_time.strftime("%Y-%m-%dT%H:%M")
        LOGGER.info("Snapshot %s (feed_ts_utc=%s)", snapshot_label, feed_ts_iso)

        snapshot_dir = _join_path(root, "rtd_gtfsrt", f"snapshot_at={snapshot_label}")
        manifest_path = _join_path(snapshot_dir, "manifest.json")
        if common.exists(manifest_path):
            LOGGER.info("Skipping snapshot %s; manifest already present.", snapshot_label)
            continue

        trip_updates_bytes, trip_updates_error = fetch_feed(args.trip_updates_url, args.timeout_sec)
        vehicle_positions_bytes, vehicle_positions_error = fetch_feed(
            args.vehicle_positions_url, args.timeout_sec
        )

        trip_updates_df, trip_quality = parse_trip_updates(
            trip_updates_bytes, feed_ts_iso, route_filter
        )
        vehicle_positions_df, vehicle_quality = parse_vehicle_positions(
            vehicle_positions_bytes, feed_ts_iso, route_filter
        )

        trip_updates_path = _join_path(snapshot_dir, "trip_updates.csv.gz")
        vehicle_positions_path = _join_path(snapshot_dir, "vehicle_positions.csv.gz")
        trip_payload = serialize_dataframe(trip_updates_df)
        vehicle_payload = serialize_dataframe(vehicle_positions_df)

        _write_bytes(trip_updates_path, trip_payload, content_type="application/gzip")
        _write_bytes(vehicle_positions_path, vehicle_payload, content_type="application/gzip")

        captured += 1
        coverage_ratio = captured / args.snapshots
        duration = time.time() - tick_start
        manifest_meta = build_manifest(
            feed_ts_iso=feed_ts_iso,
            snapshot_label=snapshot_label,
            trip_updates_path=trip_updates_path,
            vehicle_positions_path=vehicle_positions_path,
            trip_updates_payload=trip_payload,
            vehicle_positions_payload=vehicle_payload,
            trip_updates_df=trip_updates_df,
            vehicle_positions_df=vehicle_positions_df,
            trip_updates_error=trip_updates_error,
            vehicle_positions_error=vehicle_positions_error,
            trip_quality=trip_quality,
            vehicle_quality=vehicle_quality,
            config={
                "snapshots": args.snapshots,
                "interval_sec": args.interval_sec,
                "timeout_sec": args.timeout_sec,
                "route_filter": sorted(route_filter) if route_filter else None,
            },
            sources={
                "trip_updates": args.trip_updates_url,
                "vehicle_positions": args.vehicle_positions_url,
            },
            duration_sec=duration,
            snapshots_captured=captured,
            snapshots_expected=args.snapshots,
            coverage_ratio=coverage_ratio,
        )
        common.write_manifest(_ensure_directory_target(snapshot_dir), manifest_meta)
        LOGGER.info(
            "Snapshot %s trip_updates=%d rows, vehicle_positions=%d rows in %.2fs.",
            snapshot_label,
            len(trip_updates_df),
            len(vehicle_positions_df),
            duration,
        )

        if index < args.snapshots - 1 and args.interval_sec:
            time.sleep(args.interval_sec)

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest RTD GTFS-Realtime snapshots.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        dest="mode",
        action="store_const",
        const="local",
        help="Write to data/raw (default).",
    )
    mode.add_argument(
        "--gcs", dest="mode", action="store_const", const="gcs", help="Write to GCS bucket."
    )
    parser.set_defaults(mode="local")

    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument(
        "--snapshots", type=int, default=1, help="Number of snapshots to capture in this run."
    )
    parser.add_argument(
        "--interval-sec",
        type=int,
        default=60,
        help="Seconds to wait between snapshots (ignored after last snapshot).",
    )
    parser.add_argument(
        "--trip-updates-url",
        default=DEFAULT_TRIP_UPDATES_URL,
        help="Trip Updates GTFS-RT feed URL.",
    )
    parser.add_argument(
        "--vehicle-positions-url",
        default=DEFAULT_VEHICLE_POSITIONS_URL,
        help="Vehicle Positions GTFS-RT feed URL.",
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=15, help="HTTP timeout in seconds for each request."
    )
    parser.add_argument(
        "--now-utc", help="Override 'now' timestamp in ISO-8601 (used for testing)."
    )
    parser.add_argument(
        "--route-filter", help="Optional comma-separated list of route_ids to retain."
    )
    return parser


def determine_base_time(now_utc: str | None) -> datetime:
    if not now_utc:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"--now-utc must be ISO-8601: {exc}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_route_filter(route_filter: str | None) -> set[str] | None:
    if not route_filter:
        return None
    routes = {route.strip() for route in route_filter.split(",") if route.strip()}
    return routes or None


def fetch_feed(url: str, timeout_sec: int) -> tuple[bytes | None, str | None]:
    try:
        response = common.http_get_with_retry(url, timeout=timeout_sec, logger=LOGGER)
    except requests.RequestException as exc:
        LOGGER.warning("Failed to fetch %s: %s", url, exc)
        return None, str(exc)
    return response.content, None


def parse_trip_updates(
    payload: bytes | None,
    feed_ts_iso: str,
    route_filter: set[str] | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not payload:
        df = pd.DataFrame(columns=TRIP_UPDATES_COLUMNS)
        return df, {"delay_outlier_count": 0}

    feed_message = gtfs_realtime_pb2.FeedMessage()
    feed_message.ParseFromString(payload)

    rows: list[dict[str, Any]] = []
    outlier_count = 0
    for entity in feed_message.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip = trip_update.trip
        route_id = trip.route_id or None
        if route_filter and (route_id is None or route_id not in route_filter):
            continue
        trip_id = trip.trip_id or None
        entity_id = entity.id or None
        schedule_relationship = gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
            trip.schedule_relationship
        )
        start_date = trip.start_date or None
        start_time = trip.start_time or None
        entity_timestamp = trip_update.timestamp

        for stu in trip_update.stop_time_update:
            stop_id = stu.stop_id or None
            stop_sequence = stu.stop_sequence if stu.HasField("stop_sequence") else None

            arrival_delay = _get_delay(stu.arrival) if stu.HasField("arrival") else None
            departure_delay = _get_delay(stu.departure) if stu.HasField("departure") else None
            if arrival_delay is not None and not _delay_in_range(arrival_delay):
                outlier_count += 1
            if departure_delay is not None and not _delay_in_range(departure_delay):
                outlier_count += 1

            event_ts = _select_event_timestamp(
                stu,
                entity_timestamp=entity_timestamp,
                fallback=feed_ts_iso,
            )

            rows.append(
                {
                    "feed_ts_utc": feed_ts_iso,
                    "entity_id": entity_id,
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "stop_id": stop_id,
                    "stop_sequence": int(stop_sequence) if stop_sequence is not None else None,
                    "arrival_delay_sec": arrival_delay,
                    "departure_delay_sec": departure_delay,
                    "schedule_relationship": schedule_relationship,
                    "event_ts_utc": event_ts,
                    "start_date": start_date,
                    "start_time": start_time,
                }
            )

    df = pd.DataFrame(rows, columns=TRIP_UPDATES_COLUMNS)
    return df, {"delay_outlier_count": outlier_count}


def parse_vehicle_positions(
    payload: bytes | None,
    feed_ts_iso: str,
    route_filter: set[str] | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not payload:
        df = pd.DataFrame(columns=VEHICLE_POSITIONS_COLUMNS)
        return df, {"in_bbox_pct": None, "out_of_bbox_count": 0}

    feed_message = gtfs_realtime_pb2.FeedMessage()
    feed_message.ParseFromString(payload)

    rows: list[dict[str, Any]] = []
    inside_bbox = 0
    outside_bbox = 0

    for entity in feed_message.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        trip = vehicle.trip
        route_id = trip.route_id or None
        if route_filter and (route_id is None or route_id not in route_filter):
            continue
        position = vehicle.position if vehicle.HasField("position") else None
        lon = position.longitude if position and position.HasField("longitude") else None
        lat = position.latitude if position and position.HasField("latitude") else None

        if lon is not None and lat is not None:
            if DENVER_LON_MIN <= lon <= DENVER_LON_MAX and DENVER_LAT_MIN <= lat <= DENVER_LAT_MAX:
                inside_bbox += 1
            else:
                outside_bbox += 1

        event_ts = (
            _epoch_to_iso(vehicle.timestamp) if vehicle.HasField("timestamp") else feed_ts_iso
        )
        vehicle_descriptor = vehicle.vehicle if vehicle.HasField("vehicle") else None

        rows.append(
            {
                "feed_ts_utc": feed_ts_iso,
                "entity_id": entity.id or None,
                "trip_id": trip.trip_id or None,
                "route_id": route_id,
                "vehicle_id": (
                    vehicle_descriptor.id if vehicle_descriptor and vehicle_descriptor.id else None
                ),
                "vehicle_label": (
                    vehicle_descriptor.label
                    if vehicle_descriptor and vehicle_descriptor.label
                    else None
                ),
                "lon": lon,
                "lat": lat,
                "bearing": position.bearing if position and position.HasField("bearing") else None,
                "speed_mps": position.speed if position and position.HasField("speed") else None,
                "event_ts_utc": event_ts,
            }
        )

    df = pd.DataFrame(rows, columns=VEHICLE_POSITIONS_COLUMNS)
    total_positions = inside_bbox + outside_bbox if rows else 0
    in_bbox_pct = (inside_bbox / total_positions * 100) if total_positions else None
    return df, {"in_bbox_pct": in_bbox_pct, "out_of_bbox_count": outside_bbox}


def serialize_dataframe(df: pd.DataFrame) -> bytes:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(csv_bytes)
    return buffer.getvalue()


def build_manifest(
    *,
    feed_ts_iso: str,
    snapshot_label: str,
    trip_updates_path: PathLike,
    vehicle_positions_path: PathLike,
    trip_updates_payload: bytes,
    vehicle_positions_payload: bytes,
    trip_updates_df: pd.DataFrame,
    vehicle_positions_df: pd.DataFrame,
    trip_updates_error: str | None,
    vehicle_positions_error: str | None,
    trip_quality: dict[str, Any],
    vehicle_quality: dict[str, Any],
    config: dict[str, Any],
    sources: dict[str, str],
    duration_sec: float,
    snapshots_captured: int,
    snapshots_expected: int,
    coverage_ratio: float,
) -> dict[str, Any]:
    files_meta = {
        "trip_updates.csv.gz": {
            "path": str(trip_updates_path),
            "row_count": int(len(trip_updates_df)),
            "bytes": common.sizeof_bytes(trip_updates_payload),
            "hash_md5": common.hash_bytes_md5(trip_updates_payload),
            "status": "ok" if trip_updates_error is None else "error",
            "error": trip_updates_error,
        },
        "vehicle_positions.csv.gz": {
            "path": str(vehicle_positions_path),
            "row_count": int(len(vehicle_positions_df)),
            "bytes": common.sizeof_bytes(vehicle_positions_payload),
            "hash_md5": common.hash_bytes_md5(vehicle_positions_payload),
            "status": "ok" if vehicle_positions_error is None else "error",
            "error": vehicle_positions_error,
        },
    }

    total_bytes = sum(meta["bytes"] for meta in files_meta.values())
    combined_hash = common.hash_bytes_md5(trip_updates_payload + vehicle_positions_payload)

    notes_parts: list[str] = []
    if trip_updates_error:
        notes_parts.append(f"Trip updates fetch failed: {trip_updates_error}")
    if vehicle_positions_error:
        notes_parts.append(f"Vehicle positions fetch failed: {vehicle_positions_error}")
    if trip_quality.get("delay_outlier_count"):
        notes_parts.append(f"Delay outliers: {trip_quality['delay_outlier_count']}")
    if vehicle_quality.get("in_bbox_pct") is not None:
        notes_parts.append(
            f"Vehicle positions in Denver bbox: {vehicle_quality['in_bbox_pct']:.1f}%"
        )
    if not notes_parts:
        notes_parts.append("Snapshot captured successfully.")

    return {
        "source": sources,
        "extract_date": feed_ts_iso[:10],
        "written_at_utc": common.utc_now_iso(),
        "feed_ts_utc": feed_ts_iso,
        "snapshot_label": snapshot_label,
        "file_count": len(files_meta),
        "row_count": sum(meta["row_count"] for meta in files_meta.values()),
        "bytes": total_bytes,
        "hash_md5": combined_hash,
        "schema_version": "v1",
        "notes": " | ".join(notes_parts),
        "snapshots_captured": snapshots_captured,
        "snapshots_expected": snapshots_expected,
        "coverage_pct": round(coverage_ratio * 100, 2),
        "files": files_meta,
        "quality": {
            "trip_updates": trip_quality,
            "vehicle_positions": vehicle_quality,
        },
        "config": config,
        "duration_sec": duration_sec,
    }


def _get_delay(arrival_or_departure: gtfs_realtime_pb2.TripUpdate.StopTimeEvent) -> int | None:
    if arrival_or_departure.HasField("delay"):
        return int(arrival_or_departure.delay)
    if arrival_or_departure.HasField("time"):
        return None
    return None


def _delay_in_range(delay: int) -> bool:
    return -3600 <= delay <= 7200


def _select_event_timestamp(
    stu: gtfs_realtime_pb2.TripUpdate.StopTimeUpdate,
    *,
    entity_timestamp: int,
    fallback: str,
) -> str:
    if stu.HasField("arrival") and stu.arrival.HasField("time"):
        return _epoch_to_iso(stu.arrival.time)
    if stu.HasField("departure") and stu.departure.HasField("time"):
        return _epoch_to_iso(stu.departure.time)
    if entity_timestamp:
        return _epoch_to_iso(entity_timestamp)
    return fallback


def _epoch_to_iso(epoch_seconds: int) -> str:
    dt = datetime.fromtimestamp(epoch_seconds, tz=UTC).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _write_bytes(path: PathLike, data: bytes, *, content_type: str) -> None:
    if _is_gcs_path(path):
        bucket, blob_path = _split_gcs_uri(path)
        common.upload_bytes_gcs(bucket, blob_path, data, content_type)
    else:
        path_obj = Path(path) if isinstance(path, str) else path
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_bytes(data)


def _join_path(base: PathLike, *parts: str) -> PathLike:
    if _is_gcs_path(base):
        root = str(base).rstrip("/")
        joined = "/".join([root] + [part.strip("/") for part in parts])
        return joined
    base_path = Path(base) if isinstance(base, str) else base
    return base_path.joinpath(*parts)


def _ensure_directory_target(path: PathLike) -> PathLike:
    if _is_gcs_path(path):
        return f"{str(path).rstrip('/')}/"
    return path


def _is_gcs_path(path: PathLike) -> bool:
    return isinstance(path, str) and path.startswith("gs://")


def _split_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {uri}")
    bucket_and_key = uri[5:]
    if "/" not in bucket_and_key:
        raise ValueError(f"GCS URI missing object path: {uri}")
    bucket, key = bucket_and_key.split("/", 1)
    return bucket, key


if __name__ == "__main__":
    raise SystemExit(main())
