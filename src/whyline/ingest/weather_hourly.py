"""CLI to snapshot hourly weather at the DIA station from Open-Meteo.

Daily weather says whether it snowed; hourly says whether it was snowing when the bus ran. Each
nightly extract covers the last --days days in UTC hours: hours older than the archive lag come
from Open-Meteo's reanalysis archive, recent ones from its forecast API (past hours only). Staging
keeps the latest extract per hour, so archive values replace forecast ones as they arrive.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io
from whyline.ingest.noaa_daily import (
    ARCHIVE_LAG_DAYS,
    DEFAULT_STATION,
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_URL,
    STATION_COORDS,
)

HOURLY = "precipitation,snowfall,temperature_2m,wind_speed_10m"
# Column order must equal the loader registry (raw_weather_hourly).
COLUMNS = ["ts_utc", "station", "precip_mm", "snowfall_mm", "temp_c", "wind_kmh", "source"]

LOGGER = io.get_logger(__name__)


def fetch_hourly(station: str, start: date, end: date, now: datetime, timeout: int) -> pd.DataFrame:
    lat, lon = STATION_COORDS[station]
    split = (now.date() - timedelta(days=ARCHIVE_LAG_DAYS)).isoformat()
    first, last = start.isoformat(), end.isoformat()
    requests_ = []
    if first < split:
        requests_.append((OPEN_METEO_ARCHIVE_URL, "open_meteo_archive", first, min(last, split)))
    if last > split:
        requests_.append((OPEN_METEO_URL, "open_meteo_forecast", max(first, split), last))
    frames = []
    for url, source, a, b in requests_:
        response = io.http_get_with_retry(
            url,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": HOURLY,
                "timezone": "GMT",
                "start_date": a,
                "end_date": b,
            },
            timeout=timeout,
            logger=LOGGER,
        )
        response.raise_for_status()
        hourly = response.json().get("hourly", {})
        frames.append(
            pd.DataFrame(
                {
                    "ts_utc": pd.to_datetime(hourly.get("time", []), utc=True),
                    "station": station,
                    "precip_mm": hourly.get("precipitation", []),
                    # Open-Meteo reports snowfall in cm; NOAA and the daily table use mm.
                    "snowfall_mm": [
                        None if v is None else round(v * 10, 2) for v in hourly.get("snowfall", [])
                    ],
                    "temp_c": hourly.get("temperature_2m", []),
                    "wind_kmh": hourly.get("wind_speed_10m", []),
                    "source": source,
                }
            )
        )
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    df = df.dropna(subset=["precip_mm", "temp_c"], how="all")
    # The archive and forecast ranges share the split day; keep the archive's hours.
    df = df.drop_duplicates("ts_utc", keep="first")
    df = df[df.ts_utc <= pd.Timestamp(now)]  # the forecast API also returns future hours
    df["ts_utc"] = df.ts_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df[COLUMNS].reset_index(drop=True)


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    now = datetime.fromisoformat(args.now_utc) if args.now_utc else datetime.now(UTC)
    end = now.date()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days)
    if args.mode == "local":
        root: Any = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"
    rel = f"weather_hourly/extract_date={end.isoformat()}/weather_hourly.csv.gz"
    path = root / rel if isinstance(root, Path) else f"{root}/{rel}"
    if io.exists(path) and not args.force:
        LOGGER.info("Skipping hourly weather; %s exists.", path)
        return 0

    df = fetch_hourly(args.station, start, end, now, args.timeout_sec)
    expected = (end - start).days * 24
    if len(df) < 0.9 * expected:
        LOGGER.warning(
            "WEATHER_HOURLY_SUSPECT %d of about %d hours; not written", len(df), expected
        )
        return 1
    io.write_csv(df, path)
    io.write_manifest(
        path,
        {
            "station": args.station,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sources": df.source.value_counts().to_dict(),
            "files": {"weather_hourly.csv.gz": {"path": str(path), "row_count": int(len(df))}},
            "written_at_utc": io.utc_now_iso(),
        },
    )
    LOGGER.info("Wrote hourly weather: %d hours from %s.", len(df), start)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot hourly weather at the DIA station.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--station", default=DEFAULT_STATION, choices=sorted(STATION_COORDS))
    parser.add_argument("--days", type=int, default=10, help="Days back from today (UTC).")
    parser.add_argument("--start", help="First date (YYYY-MM-DD) for a backfill; overrides --days.")
    parser.add_argument("--force", action="store_true", help="Rewrite today's extract.")
    parser.add_argument("--now-utc", help="Override 'now' in ISO-8601 (for testing).")
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
