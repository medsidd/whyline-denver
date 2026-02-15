"""CLI to ingest RTD GTFS static feed."""

from __future__ import annotations

import argparse
import csv
import io
import ssl
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Union
from urllib import request

import certifi

from whylinedenver.ingest import common

DEFAULT_GTFS_URL = "https://www.rtd-denver.com/files/gtfs/google_transit.zip"
CORE_REQUIRED_FILES = ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]
OPTIONAL_CALENDAR_FILES = ["calendar.txt", "calendar_dates.txt"]
ALWAYS_COPY_FILES = ["shapes.txt"]

REQUIRED_COLUMNS = {
    "stops.txt": {"stop_id", "stop_name", "stop_lat", "stop_lon"},
    "routes.txt": {"route_id", "route_short_name", "route_long_name"},
    "trips.txt": {"trip_id", "route_id", "service_id"},
    "stop_times.txt": {"trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"},
}

LOGGER = common.get_logger(__name__)
PathLike = Union[str, Path]


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or datetime.now(UTC).date().isoformat()
    try:
        datetime.strptime(extract_date, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"--extract-date must be YYYY-MM-DD: {exc}") from exc

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    date_dir = _join_path(root, "rtd_gtfs", f"extract_date={extract_date}")
    zip_path = _join_path(date_dir, "gtfs.zip")
    gtfs_dir = _join_path(date_dir, "gtfs")
    current_zip_path = _join_path(root, "rtd_gtfs", "current", "gtfs.zip")

    if common.exists(zip_path):
        LOGGER.info("Skipping download; %s already exists.", zip_path)
        return 0

    LOGGER.info("Downloading GTFS feed from %s", args.url)
    zip_bytes = _download_zip(args.url)
    zip_md5 = common.hash_bytes_md5(zip_bytes)
    zip_size = common.sizeof_bytes(zip_bytes)

    LOGGER.info("Writing archive to %s", zip_path)
    _write_bytes(zip_path, zip_bytes, content_type="application/zip")

    LOGGER.info("Extracting required TXT files")
    extracted_files = _extract_required_files(zip_bytes)
    row_counts = _validate_files(extracted_files)

    for filename, payload in extracted_files.items():
        target_path = _join_path(gtfs_dir, filename)
        LOGGER.info("Writing %s -> %s", filename, target_path)
        _write_bytes(target_path, payload, content_type="text/plain")

    LOGGER.info("Updating current pointer %s", current_zip_path)
    _write_bytes(current_zip_path, zip_bytes, content_type="application/zip")

    manifest_meta = {
        "source": args.url,
        "extract_date": extract_date,
        "written_at_utc": common.utc_now_iso(),
        "file_count": 1 + len(extracted_files),
        "row_count": sum(row_counts.values()),
        "bytes": zip_size,
        "hash_md5": zip_md5,
        "schema_version": "v1",
        "notes": "Contains RTD GTFS static archive and extracted text files.",
        "txt_rows": row_counts,
    }
    LOGGER.info("Writing manifest with row counts: %s", row_counts)
    manifest_target = _ensure_directory_target(date_dir)
    common.write_manifest(manifest_target, manifest_meta)

    LOGGER.info("GTFS static ingest complete.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest RTD GTFS static feed.")
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
        "--extract-date", help="Extraction date YYYY-MM-DD (defaults to today UTC)."
    )
    parser.add_argument("--url", default=DEFAULT_GTFS_URL, help="GTFS static ZIP URL.")
    return parser


def _download_zip(url: str) -> bytes:
    context = ssl.create_default_context(cafile=certifi.where())
    # RTD requires a User-Agent header to prevent blocking
    req = request.Request(
        url,
        headers={"User-Agent": "WhyLineDenver/1.0 (https://github.com/medsidd/whyline-denver)"},
    )
    with request.urlopen(req, context=context) as resp:
        return resp.read()


def _extract_required_files(zip_bytes: bytes) -> dict[str, bytes]:
    extracted: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        missing_core = [name for name in CORE_REQUIRED_FILES if name not in names]
        if missing_core:
            raise ValueError(f"Archive missing required files: {missing_core}")

        calendar_present = [name for name in OPTIONAL_CALENDAR_FILES if name in names]
        if not calendar_present:
            raise ValueError("Archive missing calendar.txt or calendar_dates.txt")

        if ALWAYS_COPY_FILES[0] not in names:
            raise ValueError("Archive missing required file: shapes.txt")

        files_to_copy = set(CORE_REQUIRED_FILES + calendar_present + ALWAYS_COPY_FILES)
        for name in files_to_copy:
            extracted[name] = zf.read(name)
    return extracted


def _validate_files(files: dict[str, bytes]) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    for name, payload in files.items():
        count = _count_rows(name, payload)
        row_counts[name] = count
        if name in CORE_REQUIRED_FILES and count <= 0:
            raise ValueError(f"{name} has no data rows.")
    return row_counts


def _count_rows(name: str, payload: bytes) -> int:
    text = payload.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError(f"{name} missing header row.") from exc

    header_set = {column.strip() for column in header}
    required_columns = REQUIRED_COLUMNS.get(name, set())
    missing_columns = required_columns - header_set
    if missing_columns:
        raise ValueError(f"{name} missing required columns: {sorted(missing_columns)}")

    return sum(1 for _ in reader)


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
    without_scheme = uri[5:]
    parts = without_scheme.split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError(f"GCS URI missing object path: {uri}")
    return parts[0], parts[1]


if __name__ == "__main__":
    raise SystemExit(main())
