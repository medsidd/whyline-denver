from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Optional

import duckdb
from google.api_core.exceptions import GoogleAPIError, NotFound
from google.cloud import storage

from whylinedenver.config import Settings
from whylinedenver.sync.export_bq_marts import ALLOWLISTED_MARTS

LOGGER = logging.getLogger(__name__)

DEFAULT_DUCKDB_PATH = Path("data/warehouse.duckdb")
DEFAULT_CACHE_ROOT = Path("data/marts_cache")
SYNC_STATE_PATH = Path("data/sync_state.json")

# Materialize hot tables; keep colder marts as views.
HOT_MARTS = {
    "mart_reliability_by_route_day",
    "mart_reliability_by_stop_hour",
    "mart_weather_impacts",
}


@dataclass(slots=True)
class RefreshResult:
    mart_name: str
    run_dates: list[str]
    materialized: bool


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh DuckDB from exported mart parquet files.")
    parser.add_argument(
        "--duckdb-path",
        default=str(DEFAULT_DUCKDB_PATH),
        help="Path to the DuckDB database (default: data/warehouse.duckdb).",
    )
    parser.add_argument(
        "--local-parquet-root",
        help=(
            "Optional local directory mirror of marts output. "
            "Structure must be marts/<mart>/run_date=YYYY-MM-DD/"
        ),
    )
    parser.add_argument(
        "--cache-root",
        default=str(DEFAULT_CACHE_ROOT),
        help=(
            "Directory used to cache Parquet files when reading from GCS "
            "(default: data/marts_cache). Ignored when --local-parquet-root is provided."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices={"DEBUG", "INFO", "WARNING", "ERROR"},
        help="Logging verbosity for the refresh run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned statements without mutating DuckDB or sync state.",
    )
    return parser.parse_args(argv)


def _load_sync_state(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
            return dict(payload.get("marts", {}))
    except json.JSONDecodeError as exc:
        LOGGER.warning("Ignoring malformed sync state (%s): %s", path, exc)
        return {}


def _write_sync_state(path: Path, state: Mapping[str, str]) -> None:
    payload = {
        "refreshed_at_utc": datetime.now(UTC).isoformat(),
        "marts": dict(state),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _collect_local_run_dates(base: Path, mart_name: str) -> tuple[list[str], str]:
    mart_root = (base / mart_name).resolve()
    if not mart_root.exists():
        LOGGER.warning("Local mart folder missing (%s); skipping", mart_root)
        return [], ""

    run_dates = sorted(
        entry.name.split("=", 1)[1]
        for entry in mart_root.glob("run_date=*")
        if entry.is_dir() and "=" in entry.name
    )
    glob = str(mart_root / "run_date=*" / "**" / "*")
    return run_dates, glob


def _cache_gcs_parquet(
    client: storage.Client,
    bucket: str,
    mart_name: str,
    cache_root: Path,
) -> list[str]:
    prefix = f"marts/{mart_name}/run_date="
    base_path = cache_root / mart_name
    base_path.mkdir(parents=True, exist_ok=True)

    run_dates: set[str] = set()

    try:
        blob_iter = client.list_blobs(bucket, prefix=prefix)
    except GoogleAPIError as exc:
        LOGGER.warning(
            "Falling back to cached parquet for %s after GCS error: %s",
            mart_name,
            exc,
        )
        cached_dates, _ = _collect_local_run_dates(cache_root, mart_name)
        if cached_dates:
            return cached_dates
        raise

    for blob in blob_iter:
        if blob.name.endswith("/"):
            continue
        parts = blob.name.split("/")
        run_part = next((part for part in parts if part.startswith("run_date=")), None)
        if not run_part:
            continue
        run_date = run_part.split("=", 1)[1]
        run_dates.add(run_date)

        local_path = base_path.joinpath(*parts[2:])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.exists() and local_path.stat().st_size == blob.size:
            continue
        try:
            blob.download_to_filename(local_path)
        except GoogleAPIError as exc:
            LOGGER.warning("Failed to download %s: %s", blob.name, exc)

    return sorted(run_dates)


def _load_export_marker(client: storage.Client, bucket: str, mart_name: str) -> str:
    blob = client.bucket(bucket).blob(f"marts/{mart_name}/last_export.json")
    try:
        payload = json.loads(blob.download_as_text())
    except NotFound:
        return ""
    except GoogleAPIError as exc:
        LOGGER.warning("Unable to read last_export.json for %s: %s", mart_name, exc)
        return ""
    except json.JSONDecodeError as exc:
        LOGGER.warning("Malformed last_export.json for %s: %s", mart_name, exc)
        return ""
    return payload.get("last_service_date") or ""


def _latest_run_date(run_dates: Iterable[str]) -> str:
    dates = sorted(d for d in run_dates if d)
    return dates[-1] if dates else ""


def _ensure_connection(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def refresh(
    *,
    settings: Settings,
    duckdb_path: Path,
    local_parquet_root: Optional[Path] = None,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    dry_run: bool = False,
) -> list[RefreshResult]:
    con = _ensure_connection(duckdb_path)
    sync_state = _load_sync_state(SYNC_STATE_PATH)
    LOGGER.debug("Current sync state: %s", sync_state)

    results: list[RefreshResult] = []
    updated_state = dict(sync_state)

    storage_client: Optional[storage.Client] = None
    if local_parquet_root is None:
        storage_client = storage.Client(project=settings.GCP_PROJECT_ID)
        cache_root = cache_root.resolve()
        cache_root.mkdir(parents=True, exist_ok=True)

    for mart_name in ALLOWLISTED_MARTS:
        marker_date = ""
        if local_parquet_root:
            run_dates, glob = _collect_local_run_dates(local_parquet_root, mart_name)
        else:
            assert storage_client is not None
            run_dates = _cache_gcs_parquet(
                storage_client, settings.GCS_BUCKET, mart_name, cache_root
            )
            glob = str(cache_root / mart_name / "run_date=*" / "**" / "*")
            marker_date = _load_export_marker(storage_client, settings.GCS_BUCKET, mart_name)

        if not glob:
            LOGGER.warning("Skipping %s; no parquet files discovered", mart_name)
            continue

        materialize = mart_name in HOT_MARTS
        statement = (
            f"CREATE OR REPLACE TABLE {mart_name} AS " f"SELECT * FROM read_parquet('{glob}')"
            if materialize
            else f"CREATE OR REPLACE VIEW {mart_name} AS " f"SELECT * FROM read_parquet('{glob}')"
        )

        LOGGER.info(
            "Refreshing %s as %s using %s",
            mart_name,
            "table" if materialize else "view",
            glob,
        )
        LOGGER.debug("Statement:\n%s", statement)

        if not dry_run:
            con.execute(statement)
            latest = _latest_run_date(run_dates)
            if not latest and not local_parquet_root:
                latest = marker_date
            if latest:
                updated_state[mart_name] = latest

        results.append(
            RefreshResult(
                mart_name=mart_name,
                run_dates=run_dates,
                materialized=materialize,
            )
        )

    if not dry_run:
        _write_sync_state(SYNC_STATE_PATH, updated_state)
    con.close()
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    local_root = Path(args.local_parquet_root).resolve() if args.local_parquet_root else None
    cache_root = Path(args.cache_root).resolve()

    try:
        refresh(
            settings=settings,
            duckdb_path=Path(args.duckdb_path),
            local_parquet_root=local_root,
            cache_root=cache_root,
            dry_run=args.dry_run,
        )
    except Exception:  # pragma: no cover - defensive top-level guard
        LOGGER.exception("DuckDB mart refresh failed")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
