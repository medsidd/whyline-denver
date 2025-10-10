"""CLI to ingest ACS 5-year estimates for Denver County tracts."""

from __future__ import annotations

import argparse
import gzip
import os
from collections.abc import Sequence
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Union

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv

from whylinedenver.ingest import common

load_dotenv(override=False)

CENSUS_BASE_URL = "https://api.census.gov/data"
DEFAULT_VARIABLES_PATH = Path(__file__).resolve().parent / "acs_variables.yml"
DEFAULT_YEAR = 2023
DEFAULT_GEO = "tract"
GEO_PREFIX = {"tract": "14000US", "bg": "15000US"}

COLUMNS_OUT = [
    "geoid",
    "name",
    "year",
    "hh_no_vehicle",
    "hh_total",
    "workers_transit",
    "workers_total",
    "persons_poverty",
    "pop_total",
    "pct_hh_no_vehicle",
    "pct_transit_commute",
    "pct_poverty",
]

PathLike = Union[str, Path]
LOGGER = common.get_logger(__name__)


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or date.today().isoformat()
    _validate_iso_date(extract_date, "--extract-date")

    var_config = load_variables(Path(args.variables_path), args.year)

    if args.mode == "local":
        root: PathLike = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    filename = f"acs_{'tract' if args.geo == 'tract' else 'bg'}.csv.gz"
    date_dir = _join_path(root, "acs", f"extract_date={extract_date}")
    output_path = _join_path(date_dir, filename)

    if common.exists(output_path):
        LOGGER.info("Skipping ingest; %s already exists.", output_path)
        return 0

    api_key = args.api_key or os.getenv("CENSUS_API_KEY")

    LOGGER.info(
        "Fetching ACS data year=%s geo=%s state=%s county=%s",
        args.year,
        args.geo,
        args.state_fips,
        args.county_fips,
    )
    rows = fetch_acs_data(
        year=args.year,
        geo=args.geo,
        state_fips=args.state_fips,
        county_fips=args.county_fips,
        variables=var_config["vars"],
        api_key=api_key,
        timeout=args.timeout_sec,
    )

    df = build_dataframe(rows, args.geo, args.year, var_config["vars"])
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    payload = gzip_compress(csv_bytes)
    _write_bytes(output_path, payload, content_type="application/gzip")

    manifest = build_manifest(
        extract_date=extract_date,
        filename=filename,
        df=df,
        payload=payload,
        args=args,
        variables=var_config["vars"],
    )
    common.write_manifest(_ensure_directory_target(date_dir), manifest)

    LOGGER.info(
        "Wrote %d rows to %s (denominator coverage %s)",
        len(df),
        output_path,
        manifest["quality"]["denominator_positive_rate"],
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest ACS 5-year estimates for Denver County.")
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
        "--year", type=int, default=DEFAULT_YEAR, help="ACS vintage year (e.g., 2023)."
    )
    parser.add_argument(
        "--geo", choices=("tract", "bg"), default=DEFAULT_GEO, help="Geography level (tract or bg)."
    )
    parser.add_argument(
        "--state-fips", default="08", help="State FIPS code (default 08 for Colorado)."
    )
    parser.add_argument(
        "--county-fips", default="031", help="County FIPS code (default 031 for Denver County)."
    )
    parser.add_argument(
        "--variables-path",
        default=str(DEFAULT_VARIABLES_PATH),
        help="Path to ACS variable YAML map.",
    )
    parser.add_argument(
        "--api-key",
        help="Census API key (falls back to CENSUS_API_KEY env var if unset).",
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=30, help="HTTP timeout seconds for Census API."
    )
    return parser


def load_variables(path: Path, year: int) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Variable configuration not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not config or "vars" not in config:
        raise ValueError(f"Variable configuration missing 'vars' section: {path}")
    if "year" in config and int(config["year"]) != year:
        LOGGER.warning(
            "Variable config year %s does not match requested year %s; continuing.",
            config["year"],
            year,
        )
    return {"vars": config["vars"]}


def fetch_acs_data(
    *,
    year: int,
    geo: str,
    state_fips: str,
    county_fips: str,
    variables: dict[str, str],
    api_key: str | None,
    timeout: int,
) -> list[list[str]]:
    dataset = "acs/acs5"
    url = f"{CENSUS_BASE_URL}/{year}/{dataset}"

    field_codes = list(variables.values())
    fields = ["NAME"] + field_codes
    params = {
        "get": ",".join(fields),
    }

    if geo == "tract":
        params["for"] = "tract:*"
        params["in"] = f"state:{state_fips} county:{county_fips}"
    else:  # block groups
        params["for"] = "block group:*"
        params["in"] = f"state:{state_fips} county:{county_fips} tract:*"

    if api_key:
        params["key"] = api_key

    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data or len(data) < 2:
        raise ValueError("Census API returned no data.")
    return data


def build_dataframe(
    data: list[list[str]],
    geo: str,
    year: int,
    variables: dict[str, str],
) -> pd.DataFrame:
    header, *rows = data
    df = pd.DataFrame(rows, columns=header)

    value_columns = list(variables.values())
    for column in value_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    alias_map = {
        "no_vehicle_households": "hh_no_vehicle",
        "total_households": "hh_total",
        "transit_commuters": "workers_transit",
        "total_commuters": "workers_total",
        "persons_below_poverty": "persons_poverty",
        "total_population": "pop_total",
    }

    for alias, output_name in alias_map.items():
        code = variables.get(alias)
        if not code:
            raise KeyError(f"Variable alias '{alias}' missing in configuration.")
        df[output_name] = df[code]

    df["name"] = df["NAME"]
    df["year"] = int(year)
    prefix = GEO_PREFIX[geo]

    state_series = df["state"]
    county_series = df["county"]
    if geo == "tract":
        tract_series = df["tract"]
        df["geoid"] = prefix + state_series + county_series + tract_series
    else:
        tract_series = df["tract"]
        block_series = df["block group"]
        df["geoid"] = prefix + state_series + county_series + tract_series + block_series

    df["pct_hh_no_vehicle"] = compute_ratio(df["hh_no_vehicle"], df["hh_total"])
    df["pct_transit_commute"] = compute_ratio(df["workers_transit"], df["workers_total"])
    df["pct_poverty"] = compute_ratio(df["persons_poverty"], df["pop_total"])

    for column in ["pct_hh_no_vehicle", "pct_transit_commute", "pct_poverty"]:
        df[column] = df[column].round(4)

    result = df[COLUMNS_OUT].copy()
    return result


def compute_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    ratio = numerator / denominator
    ratio = ratio.where(denominator > 0)
    return ratio


def build_manifest(
    *,
    extract_date: str,
    filename: str,
    df: pd.DataFrame,
    payload: bytes,
    args: argparse.Namespace,
    variables: dict[str, str],
) -> dict[str, Any]:
    denom_rates = {
        "hh_total": float((df["hh_total"] > 0).mean()),
        "workers_total": float((df["workers_total"] > 0).mean()),
        "pop_total": float((df["pop_total"] > 0).mean()),
    }
    return {
        "source": "https://api.census.gov",
        "extract_date": extract_date,
        "written_at_utc": common.utc_now_iso(),
        "file_count": 1,
        "row_count": int(len(df)),
        "bytes": common.sizeof_bytes(payload),
        "hash_md5": common.hash_bytes_md5(payload),
        "schema_version": "v1",
        "notes": f"ACS {args.year} {args.geo} level for state {args.state_fips} county {args.county_fips}",
        "year": int(args.year),
        "geography": args.geo,
        "variables": variables,
        "quality": {
            "denominator_positive_rate": denom_rates,
        },
        "files": {
            filename: {
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


def _validate_iso_date(value: str, flag: str) -> None:
    if value is None:
        return
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


if __name__ == "__main__":
    raise SystemExit(main())
