"""CLI to snapshot RTD's monthly ridership and service from the National Transit Database.

Reads FTA's monthly module data (Socrata dataset 8bui-9xvu) for RTD (ntd_id 80006): unlinked
passenger trips, vehicle revenue miles and hours, and vehicles in maximum service, by mode, type
of service and month, from 2002. NTD publishes monthly with a lag of about two months and revises
earlier months, so each extract is the full history; one extract a week is enough.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io

DEFAULT_URL = "https://data.transportation.gov/resource/8bui-9xvu.json"
RTD_NTD_ID = "80006"
PAGE_SIZE = 5000
MIN_ROWS = 1500  # 1,633 on 2026-11-02
REFRESH_DAYS = 7

# Column order must equal the loader registry (raw_ntd_monthly).
COLUMNS = ["month", "mode", "tos", "mode_group", "upt", "vrm", "vrh", "voms"]
SOURCE_FIELDS = {"date": "month", "_3_mode": "mode_group"}

LOGGER = io.get_logger(__name__)


def fetch_rows(url: str, timeout: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while True:
        page = io.http_get_with_retry(
            url,
            params={
                "ntd_id": RTD_NTD_ID,
                "$select": "date,mode,tos,_3_mode,upt,vrm,vrh,voms",
                "$order": "date,mode,tos",
                "$limit": PAGE_SIZE,
                "$offset": len(rows),
            },
            timeout=timeout,
            logger=LOGGER,
        ).json()
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows


def to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows).rename(columns=SOURCE_FIELDS).reindex(columns=COLUMNS)
    df["month"] = df["month"].str[:10]
    for col in ("upt", "vrm", "vrh", "voms"):
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")
    return df


def _path(root: Any, extract_date: str) -> Any:
    rel = f"ntd_monthly/extract_date={extract_date}/ntd_monthly.csv.gz"
    return root / rel if isinstance(root, Path) else f"{root}/{rel}"


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    today = date.fromisoformat(args.extract_date) if args.extract_date else date.today()
    if args.mode == "local":
        root: Any = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"
    recent = [_path(root, (today - timedelta(days=d)).isoformat()) for d in range(REFRESH_DAYS)]
    if not args.force and any(io.exists(p) for p in recent):
        LOGGER.info("Skipping NTD; extracted within %d days.", REFRESH_DAYS)
        return 0

    df = to_frame(fetch_rows(args.url, args.timeout_sec))
    if len(df) < MIN_ROWS:
        LOGGER.warning("NTD_SUSPECT only %d rows for ntd_id %s; not written", len(df), RTD_NTD_ID)
        return 1
    path = _path(root, today.isoformat())
    io.write_csv(df, path)
    io.write_manifest(
        path,
        {
            "source": args.url,
            "ntd_id": RTD_NTD_ID,
            "extract_date": today.isoformat(),
            "latest_month": df["month"].max(),
            "files": {"ntd_monthly.csv.gz": {"path": str(path), "row_count": int(len(df))}},
            "written_at_utc": io.utc_now_iso(),
        },
    )
    LOGGER.info("Wrote NTD: %d rows through %s.", len(df), df["month"].max())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot RTD's NTD monthly ridership.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--extract-date", help="Override today's date (YYYY-MM-DD).")
    parser.add_argument("--force", action="store_true", help="Fetch even if extracted this week.")
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
