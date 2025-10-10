"""CLI to ingest Denver sidewalks feature layer."""

from __future__ import annotations

import argparse
import gzip
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Union

import pandas as pd
from pyproj import Transformer

from whylinedenver.ingest import common

DEFAULT_SOURCE_URL = (
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_TRANS_SIDEWALKS_L/FeatureServer/143"
)

OUTPUT_FILENAME = "sidewalks.csv.gz"
COLUMNS = [
    "sidewalk_id",
    "class",
    "status",
    "material",
    "year_built",
    "lon_start",
    "lat_start",
    "lon_end",
    "lat_end",
    "length_m",
    "centroid_lon",
    "centroid_lat",
]

PathLike = Union[str, Path]

LOGGER = common.get_logger(__name__)


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or date.today().isoformat()
    _validate_iso_date(extract_date, "--extract-date")

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    date_dir = _join_path(root, "denver_sidewalks", f"extract_date={extract_date}")
    output_path = _join_path(date_dir, OUTPUT_FILENAME)

    if common.exists(output_path):
        LOGGER.info("Skipping ingest; %s already exists.", output_path)
        return 0

    LOGGER.info("Fetching sidewalks from %s", args.source_url)
    features = list(fetch_features(args.source_url, args.timeout_sec))
    LOGGER.info("Retrieved %d features.", len(features))

    records, stats = normalize_records(features)
    LOGGER.info(
        "Normalized segments: %d rows; positive_length_pct=%.2f%%",
        len(records),
        stats.positive_length_pct,
    )

    df = pd.DataFrame(records, columns=COLUMNS)
    payload = gzip_compress(df.to_csv(index=False).encode("utf-8"))
    _write_bytes(output_path, payload, content_type="application/gzip")

    manifest = build_manifest(
        extract_date=extract_date,
        source_url=args.source_url,
        payload=payload,
        df=df,
        stats=stats,
    )
    common.write_manifest(_ensure_directory_target(date_dir), manifest)
    LOGGER.info(
        "Wrote %d segments to %s (total_km=%.2f)",
        len(df),
        output_path,
        stats.total_length_km,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Denver sidewalks dataset.")
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
        "--source-url", default=DEFAULT_SOURCE_URL, help="ArcGIS FeatureServer layer URL."
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=60, help="HTTP timeout for data requests."
    )
    return parser


def fetch_features(source_url: str, timeout: int) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    params = {
        "where": "1=1",
        "outFields": ",".join(
            [
                "OBJECTID",
                "SIDEWALKTYPE",
                "SIDEWALKSTATUS",
                "SURFACE",
                "BUILTYEAR",
                "STREETNAME",
                "FROMNAME",
                "TONAME",
                "FACILITYID",
            ]
        ),
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
    }

    while True:
        batch_params = {
            **params,
            "resultOffset": offset,
            "resultRecordCount": 2000,
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
    positive_length: int
    total_length_km: float

    @property
    def positive_length_pct(self) -> float:
        return _pct(self.positive_length, self.total)


def normalize_records(features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Stats]:
    transformer = Transformer.from_crs(4326, 26913, always_xy=True)
    records: list[dict[str, Any]] = []
    positive_length = 0
    total_length_m = 0.0

    for feature in features:
        attr = feature.get("attributes", {})
        geometry = feature.get("geometry", {})
        paths = geometry.get("paths") or []
        if not paths:
            continue

        flat_coords = _flatten_paths(paths)
        start_lon, start_lat = flat_coords[0]
        end_lon, end_lat = flat_coords[-1]
        centroid_lon, centroid_lat = _compute_centroid(flat_coords)
        length_m = _projected_length(flat_coords, transformer)
        if length_m > 0:
            positive_length += 1
        total_length_m += length_m

        record = {
            "sidewalk_id": _format_str(attr.get("FACILITYID")) or _format_str(attr.get("OBJECTID")),
            "class": _format_str(attr.get("SIDEWALKTYPE")),
            "status": _format_str(attr.get("SIDEWALKSTATUS")),
            "material": _format_str(attr.get("SURFACE")),
            "year_built": _safe_int(attr.get("BUILTYEAR")),
            "lon_start": start_lon,
            "lat_start": start_lat,
            "lon_end": end_lon,
            "lat_end": end_lat,
            "length_m": length_m,
            "centroid_lon": centroid_lon,
            "centroid_lat": centroid_lat,
        }
        records.append(record)

    stats = Stats(
        total=len(features),
        positive_length=positive_length,
        total_length_km=total_length_m / 1000 if total_length_m else 0.0,
    )
    return records, stats


def build_manifest(
    *,
    extract_date: str,
    source_url: str,
    payload: bytes,
    df: pd.DataFrame,
    stats: Stats,
) -> dict[str, Any]:
    return {
        "source": source_url,
        "extract_date": extract_date,
        "written_at_utc": common.utc_now_iso(),
        "file_count": 1,
        "row_count": int(len(df)),
        "bytes": common.sizeof_bytes(payload),
        "hash_md5": common.hash_bytes_md5(payload),
        "schema_version": "v1",
        "notes": f"Total network length {stats.total_length_km:.2f} km; positive length pct {stats.positive_length_pct:.2f}%.",
        "quality": {
            "positive_length_pct": stats.positive_length_pct,
            "segment_count": stats.total,
            "total_length_km": stats.total_length_km,
        },
        "files": {
            OUTPUT_FILENAME: {
                "row_count": int(len(df)),
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


def _flatten_paths(paths: list[list[list[float]]]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for path in paths:
        for lon, lat in path:
            coords.append((float(lon), float(lat)))
    return coords


def _compute_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    if not coords:
        return 0.0, 0.0
    lon_sum = sum(lon for lon, _ in coords)
    lat_sum = sum(lat for _, lat in coords)
    count = len(coords)
    return lon_sum / count, lat_sum / count


def _projected_length(coords: list[tuple[float, float]], transformer: Transformer) -> float:
    if len(coords) < 2:
        return 0.0

    projected = [transformer.transform(lon, lat) for lon, lat in coords]
    total = 0.0
    for (x1, y1), (x2, y2) in zip(projected, projected[1:], strict=False):
        dx = x2 - x1
        dy = y2 - y1
        total += (dx**2 + dy**2) ** 0.5
    return total


def _validate_iso_date(value: str, flag: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"{flag} must be YYYY-MM-DD: {exc}")


def _format_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip().lower()


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100


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


if __name__ == "__main__":
    raise SystemExit(main())
