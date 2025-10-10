"""CLI to ingest Denver traffic accidents dataset."""

from __future__ import annotations

import argparse
import gzip
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from math import atan, exp, pi
from pathlib import Path
from typing import Any, Union

import pandas as pd

from whylinedenver.ingest import common

DEFAULT_SOURCE_URL = (
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_CRIME_TRAFFICACCIDENTS5YR_P/FeatureServer/325"
)
DEFAULT_YEARS_BACK = 5
BATCH_SIZE = 2000
DENVER_LON_MIN = -105.2
DENVER_LON_MAX = -104.5
DENVER_LAT_MIN = 39.4
DENVER_LAT_MAX = 40.2

OUTPUT_FILENAME = "crashes.csv.gz"
COLUMNS = [
    "crash_id",
    "event_ts_utc",
    "severity",
    "severity_text",
    "lat",
    "lon",
    "roadway_name",
    "on_route",
    "off_route",
    "bike_involved",
    "ped_involved",
]

PathLike = Union[str, Path]

LOGGER = common.get_logger(__name__)


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or date.today().isoformat()
    _validate_iso_date(extract_date, "--extract-date")

    since_date = args.since or _default_since(extract_date)
    _validate_iso_date(since_date, "--since")

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    date_dir = _join_path(root, "denver_crashes", f"extract_date={extract_date}")
    output_path = _join_path(date_dir, OUTPUT_FILENAME)
    manifest_target = _ensure_directory_target(date_dir)

    if common.exists(output_path):
        LOGGER.info("Skipping ingest; %s already exists.", output_path)
        return 0

    LOGGER.info("Fetching crashes since %s from %s", since_date, args.source_url)
    features = list(fetch_features(args.source_url, since_date, args.timeout_sec))
    LOGGER.info("Retrieved %d feature records.", len(features))

    records, stats = normalize_records(features)
    LOGGER.info(
        "Normalized records: %d rows; dropped_no_location=%d; timestamp_success_pct=%.2f%%",
        len(records),
        stats.dropped_no_location,
        stats.timestamp_success_pct,
    )

    df = pd.DataFrame(records, columns=COLUMNS)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    payload = gzip_compress(csv_bytes)

    _write_bytes(output_path, payload, content_type="application/gzip")

    manifest = build_manifest(
        extract_date=extract_date,
        since_date=since_date,
        source_url=args.source_url,
        payload=payload,
        df=df,
        stats=stats,
    )
    common.write_manifest(manifest_target, manifest)
    LOGGER.info(
        "Wrote %d rows to %s (bytes=%d hash=%s)",
        len(df),
        output_path,
        len(payload),
        manifest["hash_md5"],
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Denver traffic accident data.")
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
    parser.add_argument("--extract-date", help="Extraction date YYYY-MM-DD (defaults to today).")
    parser.add_argument(
        "--since",
        help=f"Lower bound inclusive for crash date (default {DEFAULT_YEARS_BACK} years ago).",
    )
    parser.add_argument(
        "--source-url", default=DEFAULT_SOURCE_URL, help="ArcGIS FeatureServer layer URL."
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=30, help="HTTP timeout for data requests."
    )
    return parser


def fetch_features(source_url: str, since_date: str, timeout: int) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    params = {
        "where": f"first_occurrence_date >= DATE '{since_date}'",
        "outFields": ",".join(
            [
                "incident_id",
                "first_occurrence_date",
                "top_traffic_accident_offense",
                "incident_address",
                "geo_lat",
                "geo_lon",
                "POINT_X",
                "POINT_Y",
                "bicycle_ind",
                "pedestrian_ind",
                "SERIOUSLY_INJURED",
                "FATALITIES",
            ]
        ),
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
        "orderByFields": "first_occurrence_date",
    }

    while True:
        batch_params = {
            **params,
            "resultOffset": offset,
            "resultRecordCount": BATCH_SIZE,
        }
        response = common.http_get_with_retry(
            f"{source_url}/query",
            params=batch_params,
            timeout=timeout,
            logger=LOGGER,
        )
        data = response.json()
        batch = data.get("features") or []
        if not batch:
            break
        features.extend(batch)
        if not data.get("exceededTransferLimit"):
            break
        offset += len(batch)

    return features


@dataclass
class Stats:
    total: int
    dropped_no_location: int
    timestamp_success: int
    timestamp_failures: int
    bbox_in: int
    bbox_total: int

    @property
    def timestamp_success_pct(self) -> float:
        return _pct(self.timestamp_success, self.total - self.dropped_no_location)

    @property
    def bbox_in_pct(self) -> float:
        return _pct(self.bbox_in, self.bbox_total)


def normalize_records(features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Stats]:
    records: list[dict[str, Any]] = []
    dropped_no_location = 0
    timestamp_success = 0
    timestamp_failures = 0
    bbox_in = 0
    bbox_total = 0

    for feat in features:
        attr = feat.get("attributes", {})
        geometry = feat.get("geometry")

        crash_id = _safe_str(attr.get("incident_id"))
        event_ts = _format_timestamp(attr.get("first_occurrence_date"))
        if event_ts is None:
            timestamp_failures += 1
        else:
            timestamp_success += 1

        severity_text, severity = _derive_severity(
            attr.get("top_traffic_accident_offense"),
            attr.get("SERIOUSLY_INJURED"),
            attr.get("FATALITIES"),
        )

        roadway_name, on_route, off_route = _parse_address(attr.get("incident_address"))

        lat, lon = _extract_lat_lon(
            attr.get("geo_lat"),
            attr.get("geo_lon"),
            attr.get("POINT_Y"),
            attr.get("POINT_X"),
            geometry,
        )

        if lat is not None and lon is not None:
            bbox_total += 1
            if DENVER_LON_MIN <= lon <= DENVER_LON_MAX and DENVER_LAT_MIN <= lat <= DENVER_LAT_MAX:
                bbox_in += 1

        if lat is None or lon is None:
            if not roadway_name:
                dropped_no_location += 1
                continue

        record = {
            "crash_id": crash_id,
            "event_ts_utc": event_ts,
            "severity": severity,
            "severity_text": severity_text,
            "lat": lat,
            "lon": lon,
            "roadway_name": roadway_name,
            "on_route": on_route,
            "off_route": off_route,
            "bike_involved": _bool_to_int(attr.get("bicycle_ind")),
            "ped_involved": _bool_to_int(attr.get("pedestrian_ind")),
        }
        records.append(record)

    stats = Stats(
        total=len(features),
        dropped_no_location=dropped_no_location,
        timestamp_success=timestamp_success,
        timestamp_failures=timestamp_failures,
        bbox_in=bbox_in,
        bbox_total=bbox_total,
    )
    return records, stats


def build_manifest(
    *,
    extract_date: str,
    since_date: str,
    source_url: str,
    payload: bytes,
    df: pd.DataFrame,
    stats: Stats,
) -> dict[str, Any]:
    row_count = int(len(df))
    min_ts = df["event_ts_utc"].dropna().min() if row_count else None
    max_ts = df["event_ts_utc"].dropna().max() if row_count else None
    notes = (
        f"Timestamp success {stats.timestamp_success_pct:.2f}% "
        f"(failures {stats.timestamp_failures}); "
        f"BBox coverage {stats.bbox_in_pct:.2f}% of {stats.bbox_total} geocoded rows."
    )
    return {
        "source": source_url,
        "extract_date": extract_date,
        "written_at_utc": common.utc_now_iso(),
        "file_count": 1,
        "row_count": row_count,
        "bytes": common.sizeof_bytes(payload),
        "hash_md5": common.hash_bytes_md5(payload),
        "schema_version": "v1",
        "notes": notes,
        "since": since_date,
        "event_ts_range": {"min": min_ts, "max": max_ts},
        "quality": {
            "timestamp_success_pct": stats.timestamp_success_pct,
            "timestamp_failures": stats.timestamp_failures,
            "dropped_no_location": stats.dropped_no_location,
            "bbox_in_pct": stats.bbox_in_pct,
            "bbox_total": stats.bbox_total,
        },
        "files": {
            OUTPUT_FILENAME: {
                "row_count": row_count,
                "bytes": common.sizeof_bytes(payload),
                "hash_md5": common.hash_bytes_md5(payload),
            }
        },
    }


def gzip_compress(data: bytes) -> bytes:
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(data)
    return buffer.getvalue()


def _derive_severity(
    severity_text_raw: str | None,
    seriously_injured: Any | None,
    fatalities: Any | None,
) -> tuple[str, int]:
    if fatalities is not None and int(fatalities) > 0:
        return "fatal", 4
    if seriously_injured is not None and int(seriously_injured) > 0:
        return "serious_injury", 3
    label = (severity_text_raw or "").strip().lower()
    if "sbi" in label:
        return "serious_injury", 3
    if "injury" in label:
        return "injury", 2
    if "fatal" in label:
        return "fatal", 4
    return "property_damage", 1


def _parse_address(address: str | None) -> tuple[str | None, str | None, str | None]:
    if not address:
        return None, None, None
    clean = address.strip()
    if not clean:
        return None, None, None
    if " / " in clean:
        on, off = clean.split(" / ", 1)
        return clean, on.strip() or None, off.strip() or None
    if " & " in clean:
        on, off = clean.split(" & ", 1)
        return clean, on.strip() or None, off.strip() or None
    return clean, clean, None


def _extract_lat_lon(
    geo_lat: float | None,
    geo_lon: float | None,
    point_y: float | None,
    point_x: float | None,
    geometry: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    lat = _safe_float(geo_lat)
    lon = _safe_float(geo_lon)
    if lat is not None and lon is not None:
        return lat, lon

    lat_point = _safe_float(point_y)
    lon_point = _safe_float(point_x)
    if lat_point is not None and lon_point is not None:
        return lat_point, lon_point

    if geometry and "x" in geometry and "y" in geometry:
        lon_wm, lat_wm = geometry["x"], geometry["y"]
        lon_trans, lat_trans = _web_mercator_to_lon_lat(lon_wm, lat_wm)
        return lat_trans, lon_trans

    return None, None


def _format_timestamp(ms_since_epoch: Any | None) -> str | None:
    if ms_since_epoch is None:
        return None
    try:
        ms_int = int(ms_since_epoch)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(ms_int / 1000, tz=UTC).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _bool_to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return 1 if int(value) != 0 else 0
    except (TypeError, ValueError):
        return 1 if str(value).strip().lower() in {"true", "t", "yes"} else 0


def _default_since(extract_date: str) -> str:
    base = datetime.strptime(extract_date, "%Y-%m-%d").date()
    return (base - timedelta(days=DEFAULT_YEARS_BACK * 365)).isoformat()


def _validate_iso_date(value: str, flag: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"{flag} must be YYYY-MM-DD: {exc}")


def _join_path(base: PathLike, *parts: str) -> PathLike:
    if isinstance(base, str) and base.startswith("gs://"):
        root = base.rstrip("/")
        joined = "/".join([root] + [part.strip("/") for part in parts])
        return joined
    base_path = Path(base) if isinstance(base, str) else base
    return base_path.joinpath(*parts)


def _ensure_directory_target(path: PathLike) -> PathLike:
    if isinstance(path, str) and path.startswith("gs://"):
        return f"{str(path).rstrip('/')}/"
    return path


def _write_bytes(path: PathLike, data: bytes, *, content_type: str) -> None:
    if isinstance(path, str) and path.startswith("gs://"):
        bucket, blob_path = _split_gcs_uri(path)
        common.upload_bytes_gcs(bucket, blob_path, data, content_type)
    else:
        path_obj = Path(path) if isinstance(path, str) else path
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_bytes(data)


def _split_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {uri}")
    bucket_and_key = uri[5:]
    if "/" not in bucket_and_key:
        raise ValueError(f"GCS URI missing object path: {uri}")
    bucket, key = bucket_and_key.split("/", 1)
    return bucket, key


def _safe_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _web_mercator_to_lon_lat(x: float, y: float) -> tuple[float, float]:
    r_major = 6378137.0
    lon = (x / r_major) * (180 / pi)
    lat_rad = 2 * atan(exp(y / r_major)) - (pi / 2)
    lat = lat_rad * (180 / pi)
    return float(lon), float(lat)


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100


if __name__ == "__main__":
    raise SystemExit(main())
