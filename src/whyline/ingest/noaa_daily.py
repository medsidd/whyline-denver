"""CLI to ingest NOAA daily weather summaries for Denver."""

from __future__ import annotations

import argparse
import csv
import gzip
import os
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Union

import pandas as pd
import requests
from dotenv import load_dotenv

from whyline.ingest import io

load_dotenv(override=False)

CDO_API_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2/data"
DEFAULT_STATION = "USW00003017"
DEFAULT_DATASET = "GHCND"
DATATYPES = ["SNOW", "PRCP", "TMIN", "TMAX", "TAVG"]
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# Fallback coordinates per GHCND station; Open-Meteo returns gridded model values, not observations.
STATION_COORDS = {DEFAULT_STATION: (39.8467, -104.6562)}
DEFAULT_LOCAL_SOURCE = Path("data/external/noaa_raw.csv")
OUTPUT_FILENAME = "weather.csv.gz"
PRECIP_BINS = [
    ("none", 0, 0),
    ("light", 0, 5),
    ("mod", 5, 20),
    ("heavy", 20, float("inf")),
]

PathLike = Union[str, Path]
LOGGER = io.get_logger(__name__)


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or date.today().isoformat()
    _validate_iso_date(extract_date, "--extract-date")
    _validate_iso_date(args.start, "--start")
    _validate_iso_date(args.end, "--end")
    if args.start > args.end:
        raise SystemExit("--start must be on or before --end")

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    # Keep earlier station extracts intact when the configured station changes.
    args.station = _extract_station_code(args.station, DEFAULT_STATION)
    date_dir = _join_path(
        root, "noaa_daily", f"extract_date={extract_date}", f"station={args.station}"
    )
    output_path = _join_path(date_dir, OUTPUT_FILENAME)

    if io.exists(output_path):
        LOGGER.info("Skipping ingest; %s already exists.", output_path)
        return 0

    token = args.token or os.getenv("NOAA_CDO_TOKEN")

    if token:
        LOGGER.info(
            "Fetching NOAA CDO data for station %s (%s–%s)",
            args.station,
            args.start,
            args.end,
        )
        try:
            raw_records = fetch_noaa_cdo(
                token=token,
                station=args.station,
                start=args.start,
                end=args.end,
                timeout=args.timeout_sec,
            )
        except requests.RequestException as exc:
            LOGGER.warning("NOAA CDO unavailable (%s); falling back to Open-Meteo.", exc)
            raw_records = []
        source_descriptor = "noaa_cdo_api"
        raw_records, filled = fill_missing_days(
            raw_records,
            station=args.station,
            start=args.start,
            end=args.end,
            timeout=args.timeout_sec,
        )
        if filled:
            source_descriptor = f"noaa_cdo_api+open_meteo_fallback ({len(filled)} days)"
    else:
        source_path = Path(args.source_path) if args.source_path else DEFAULT_LOCAL_SOURCE
        LOGGER.info("Loading local NOAA CSV from %s", source_path)
        raw_records = load_local_csv(
            path=source_path,
            station=args.station,
            start=args.start,
            end=args.end,
        )
        source_descriptor = str(source_path)

    df = build_dataframe(raw_records, args.start, args.end, args.station)
    if df["precip_mm"].isna().all():
        raise RuntimeError(
            f"No precipitation observations for {args.station} in {args.start}–{args.end}; "
            "refusing to publish an empty weather extract. Check NOAA station coverage."
        )

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    payload = gzip_compress(csv_bytes)
    _write_bytes(output_path, payload, content_type="application/gzip")

    manifest = build_manifest(
        extract_date=extract_date,
        start=args.start,
        end=args.end,
        source=source_descriptor,
        payload=payload,
        df=df,
    )
    io.write_manifest(_ensure_directory_target(date_dir), manifest)

    LOGGER.info(
        "Wrote %d rows to %s (missing precip %.3f)",
        len(df),
        output_path,
        manifest["quality"]["missing_rates"].get("precip_mm", 0.0),
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest NOAA daily weather summaries.")
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

    parser.add_argument("--bucket", help="GCS bucket name (required for --gcs).")
    parser.add_argument("--extract-date", help="Extraction date YYYY-MM-DD (defaults to today).")
    parser.add_argument("--start", required=True, help="Start date (inclusive) YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="End date (inclusive) YYYY-MM-DD.")
    parser.add_argument(
        "--station", default=DEFAULT_STATION, help="NOAA station ID (default: Denver airport)."
    )
    parser.add_argument(
        "--token",
        help="NOAA CDO API token (falls back to NOAA_CDO_TOKEN env var if unspecified).",
    )
    parser.add_argument(
        "--source-path",
        help=f"Metric-unit local CSV (default {DEFAULT_LOCAL_SOURCE}). Used when --token absent.",
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=60, help="HTTP timeout for API requests."
    )
    return parser


def fetch_noaa_cdo(
    *,
    token: str,
    station: str,
    start: str,
    end: str,
    timeout: int,
) -> list[dict[str, Any]]:
    headers = {"token": token}
    records: dict[str, dict[str, Any]] = defaultdict(dict)
    limit = 1000
    offset = 1
    station_id = station if station.startswith("GHCND:") else f"GHCND:{station}"

    while True:
        params = {
            "datasetid": DEFAULT_DATASET,
            "stationid": station_id,
            "startdate": f"{start}T00:00:00",
            "enddate": f"{end}T23:59:59",
            "limit": limit,
            "offset": offset,
            "units": "metric",
        }
        for dt in DATATYPES:
            params.setdefault("datatypeid", []).append(dt)

        # NOAA CDO is often slow or briefly unavailable; retry before failing the nightly ingest.
        response = io.http_get_with_retry(
            CDO_API_URL,
            headers=headers,
            params=params,
            timeout=timeout,
            retries=4,
            backoff_factor=3.0,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            break

        for item in results:
            day = item.get("date", "")[:10]
            if not day:
                continue
            entry = records.setdefault(
                day, {"date": day, "station": _extract_station_code(item.get("station"), station)}
            )
            entry[item.get("datatype")] = item.get("value")

        if len(results) < limit:
            break
        offset += limit

    return list(records.values())


def fill_missing_days(
    records: list[dict[str, Any]],
    *,
    station: str,
    start: str,
    end: str,
    timeout: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fill days without NOAA precipitation from Open-Meteo; NOAA values always win.

    shortcut: filled days are not flagged in BigQuery (no source column); the next run with
    NOAA data replaces them because the nightly window re-fetches the last 30 days.
    """
    merged = {r["date"]: dict(r) for r in records if r.get("date")}
    missing = [
        day
        for day in pd.date_range(start=start, end=end, freq="D").strftime("%Y-%m-%d")
        if _to_float(merged.get(day, {}).get("PRCP")) is None
    ]
    if not missing:
        return records, []
    if station not in STATION_COORDS:
        LOGGER.warning(
            "No fallback coordinates for station %s; leaving %d days empty.", station, len(missing)
        )
        return records, []
    try:
        fallback = fetch_open_meteo(station=station, start=start, end=end, timeout=timeout)
    except requests.RequestException as exc:
        LOGGER.warning("Open-Meteo fallback unavailable (%s).", exc)
        return records, []

    filled: list[str] = []
    for day in missing:
        values = fallback.get(day)
        if not values or values.get("PRCP") is None:
            continue
        entry = merged.setdefault(day, {"date": day, "station": station})
        for key, value in values.items():
            if _to_float(entry.get(key)) is None:
                entry[key] = value
        filled.append(day)
    LOGGER.info(
        "Filled %d of %d days without NOAA precipitation from Open-Meteo.",
        len(filled),
        len(missing),
    )
    return list(merged.values()), filled


def fetch_open_meteo(
    *,
    station: str,
    start: str,
    end: str,
    timeout: int,
) -> dict[str, dict[str, Any]]:
    """Daily Open-Meteo values keyed by date, in NOAA datatype names and units (mm, Celsius)."""
    lat, lon = STATION_COORDS[station]
    response = io.http_get_with_retry(
        OPEN_METEO_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "precipitation_sum,snowfall_sum,temperature_2m_max,"
            "temperature_2m_min,temperature_2m_mean",
            "timezone": "America/Denver",
            "start_date": start,
            "end_date": end,
        },
        timeout=timeout,
        logger=LOGGER,
    )
    response.raise_for_status()
    daily = response.json().get("daily", {})
    snow_cm = daily.get("snowfall_sum", [])
    return {
        day: {
            "PRCP": daily["precipitation_sum"][i],
            # Open-Meteo reports snowfall in cm; NOAA SNOW is mm.
            "SNOW": None if snow_cm[i] is None else round(snow_cm[i] * 10, 2),
            "TMAX": daily["temperature_2m_max"][i],
            "TMIN": daily["temperature_2m_min"][i],
            "TAVG": daily["temperature_2m_mean"][i],
        }
        for i, day in enumerate(daily.get("time", []))
    }


def load_local_csv(
    *,
    path: Path,
    station: str,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Local NOAA data file not found: {path}")

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date_value = row.get("DATE") or row.get("date")
            if not date_value:
                continue
            day = date_value[:10]
            if day < start or day > end:
                continue
            entry: dict[str, Any] = {"date": day, "station": row.get("STATION", station)}
            for key in DATATYPES:
                entry[key] = row.get(key)
            records.append(entry)

    return records


def build_dataframe(
    records: list[dict[str, Any]],
    start: str,
    end: str,
    station: str,
) -> pd.DataFrame:
    date_index = pd.date_range(start=start, end=end, freq="D")
    mapped = {record["date"]: record for record in records if "date" in record}

    rows: list[dict[str, Any]] = []
    for dt in date_index.strftime("%Y-%m-%d"):
        base = mapped.get(dt, {"date": dt, "station": station})
        row = {
            "date": dt,
            "station": base.get("station") or station,
            "snow_mm": _to_float(base.get("SNOW")),
            "precip_mm": _to_float(base.get("PRCP")),
            "tmin_c": _to_float(base.get("TMIN")),
            "tmax_c": _to_float(base.get("TMAX")),
            "tavg_c": _to_float(base.get("TAVG")),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # CDO units=metric already returns mm and Celsius; never infer scale from magnitude.
    for column in ["snow_mm", "precip_mm", "tmin_c", "tmax_c", "tavg_c"]:
        df[column] = df[column].astype(float)
    df["tavg_c"] = df["tavg_c"].combine_first((df["tmin_c"] + df["tmax_c"]) / 2)
    # Use Int64 (nullable integer) to preserve integer format even with NULLs
    df["snow_day"] = (
        df["snow_mm"].apply(lambda x: None if pd.isna(x) else int(x >= 1.0)).astype("Int64")
    )
    df["precip_bin"] = df["precip_mm"].apply(_precip_category)
    for column in ["snow_mm", "precip_mm", "tmin_c", "tmax_c", "tavg_c"]:
        if column in df:
            df[column] = df[column].round(2)
    df = df[COLUMNS_IN_ORDER()]
    return df


def build_manifest(
    *,
    extract_date: str,
    start: str,
    end: str,
    source: str,
    payload: bytes,
    df: pd.DataFrame,
) -> dict[str, Any]:
    missing_rates = {
        column: float(df[column].isna().mean())
        for column in [
            "snow_mm",
            "precip_mm",
            "tmin_c",
            "tmax_c",
            "tavg_c",
            "snow_day",
            "precip_bin",
        ]
    }
    return {
        "source": source,
        "extract_date": extract_date,
        "written_at_utc": io.utc_now_iso(),
        "file_count": 1,
        "row_count": int(len(df)),
        "bytes": io.sizeof_bytes(payload),
        "hash_md5": io.hash_bytes_md5(payload),
        "schema_version": "v1",
        "notes": f"Coverage {start} to {end}",
        "date_range": {"start": start, "end": end},
        "quality": {
            "missing_rates": missing_rates,
        },
        "files": {
            OUTPUT_FILENAME: {
                "row_count": int(len(df)),
                "bytes": io.sizeof_bytes(payload),
                "hash_md5": io.hash_bytes_md5(payload),
            }
        },
    }


def gzip_compress(data: bytes) -> bytes:
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(data)
    return buffer.getvalue()


def _precip_category(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    mm = float(value)
    if mm <= 0:
        return "none"
    if mm <= 5:
        return "light"
    if mm <= 20:
        return "mod"
    return "heavy"


def _to_float(value: Any) -> float | None:
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_station_code(value: str | None, default: str) -> str:
    if not value:
        return default
    return value.split(":")[-1]


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
        io.upload_bytes_gcs(bucket, blob_path, data, content_type)
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


def COLUMNS_IN_ORDER() -> list[str]:
    return [
        "date",
        "station",
        "snow_mm",
        "precip_mm",
        "tmin_c",
        "tmax_c",
        "tavg_c",
        "snow_day",
        "precip_bin",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
