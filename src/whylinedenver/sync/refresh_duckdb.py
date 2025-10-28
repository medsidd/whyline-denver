from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Optional

import duckdb
from google.api_core.exceptions import GoogleAPIError, NotFound
from google.cloud import storage

from whylinedenver.config import Settings
from whylinedenver.sync.constants import ALLOWLISTED_MARTS
from whylinedenver.sync.state_store import SyncStateUploadError, load_sync_state, write_sync_state

LOGGER = logging.getLogger(__name__)

DEFAULT_DUCKDB_PATH = Path("data/warehouse.duckdb")
DEFAULT_CACHE_ROOT = Path("data/marts")
SYNC_STATE_PATH = Path("data/sync_state.json")

DUCKDB_MAX_AGE_DAYS = int(os.getenv("DUCKDB_MAX_AGE_DAYS", "90"))

# Materialize hot tables; keep colder marts as views.
HOT_MARTS = {
    "mart_reliability_by_route_day",
    "mart_reliability_by_stop_hour",
    "mart_weather_impacts",
}

# Snapshot marts without time dimensions should only sync the latest run_date
# to avoid duplicating the same data (only build_run_at differs between exports).
# Partitioned marts and snapshot marts with time dimensions (e.g., as_of_date)
# should sync all run_dates to maintain historical data.
LATEST_RUN_DATE_ONLY_MARTS = {
    "mart_access_score_by_stop",
    "mart_vulnerability_by_stop",
    "mart_priority_hotspots",
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


def _prepare_sync_state(path: Path) -> tuple[dict, dict, str | None]:
    default: dict[str, object] = {}

    remote_state = load_sync_state(path=path, prefer_gcs=True)
    if remote_state:
        serialized = json.dumps(remote_state, indent=2, sort_keys=True) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        default = dict(remote_state)

    local_state = load_sync_state(path=path, prefer_gcs=False) or {}
    state = dict(local_state or default)

    if default:
        state.setdefault("duckdb_synced_at_utc", default.get("duckdb_synced_at_utc"))
        state.setdefault("bigquery_updated_at_utc", default.get("bigquery_updated_at_utc"))
        existing_marts = state.get("marts")
        if not isinstance(existing_marts, dict) or not existing_marts:
            state["marts"] = default.get("marts", {})

    marts_state = state.get("marts")
    if not isinstance(marts_state, dict):
        marts_state = {}
        state["marts"] = marts_state
    bigquery_updated_at = state.get("bigquery_updated_at_utc")
    return state, marts_state, bigquery_updated_at


def _resolve_mart_sources(
    *,
    mart_name: str,
    local_parquet_root: Optional[Path],
    cache_root: Path,
    storage_client: Optional[storage.Client],
    bucket: str,
    use_latest_only: bool,
) -> tuple[list[str], list[str], str]:
    marker_date = ""
    run_dates: list[str] = []
    paths: list[str] = []

    if local_parquet_root:
        base_path = local_parquet_root.resolve()
        run_dates, _ = _collect_local_run_dates(local_parquet_root, mart_name)
    else:
        assert storage_client is not None
        base_path = cache_root.resolve()
        run_dates = _cache_gcs_parquet(storage_client, bucket, mart_name, cache_root)
        marker_date = _load_export_marker(storage_client, bucket, mart_name)

    run_dates = sorted(run_dates)

    if run_dates and DUCKDB_MAX_AGE_DAYS > 0 and not use_latest_only:
        cutoff = (date.today() - timedelta(days=DUCKDB_MAX_AGE_DAYS)).isoformat()
        filtered = [rd for rd in run_dates if rd >= cutoff]
        if filtered:
            if filtered != run_dates:
                LOGGER.info(
                    "Trimming %s run_dates to last %s days (%d → %d)",
                    mart_name,
                    DUCKDB_MAX_AGE_DAYS,
                    len(run_dates),
                    len(filtered),
                )
            run_dates = filtered

    if use_latest_only and run_dates:
        run_dates = [_latest_run_date(run_dates)]

    if run_dates:
        for rd in run_dates:
            paths.append(str(base_path / mart_name / f"run_date={rd}" / "**" / "*"))
    else:
        paths.append(str(base_path / mart_name / "run_date=*" / "**" / "*"))

    return run_dates, paths, marker_date


def _refresh_mart(
    *,
    con: duckdb.DuckDBPyConnection,
    mart_name: str,
    run_dates: list[str],
    paths: list[str],
    materialize: bool,
    sync_strategy: str,
    dry_run: bool,
) -> RefreshResult:
    if len(paths) == 1:
        source_expr = f"read_parquet('{paths[0]}')"
    else:
        array_literal = ", ".join(f"'{path}'" for path in paths)
        source_expr = f"read_parquet(ARRAY[{array_literal}])"

    statement = (
        f"CREATE OR REPLACE TABLE {mart_name} AS SELECT * FROM {source_expr}"
        if materialize
        else f"CREATE OR REPLACE VIEW {mart_name} AS SELECT * FROM {source_expr}"
    )
    LOGGER.info(
        "Refreshing %s as %s using %s paths (%s)",
        mart_name,
        "table" if materialize else "view",
        len(paths),
        sync_strategy,
    )
    LOGGER.debug("Statement:\n%s", statement)
    if not dry_run:
        con.execute(statement)
    return RefreshResult(mart_name=mart_name, run_dates=run_dates, materialized=materialize)


def refresh(
    *,
    settings: Settings,
    duckdb_path: Path,
    local_parquet_root: Optional[Path] = None,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    dry_run: bool = False,
) -> list[RefreshResult]:
    con = _ensure_connection(duckdb_path)
    state, marts_state, bigquery_updated_at = _prepare_sync_state(SYNC_STATE_PATH)
    LOGGER.debug("Current sync state marts: %s", marts_state)
    LOGGER.debug("BigQuery last updated: %s", bigquery_updated_at)

    results: list[RefreshResult] = []

    storage_client: Optional[storage.Client] = None
    if local_parquet_root is None:
        storage_client = storage.Client(project=settings.GCP_PROJECT_ID)
        cache_root = cache_root.resolve()
        cache_root.mkdir(parents=True, exist_ok=True)

    for mart_name in ALLOWLISTED_MARTS:
        marker_date = ""
        use_latest_only = mart_name in LATEST_RUN_DATE_ONLY_MARTS

        run_dates, paths, marker_date = _resolve_mart_sources(
            mart_name=mart_name,
            local_parquet_root=local_parquet_root,
            cache_root=cache_root,
            storage_client=storage_client,
            bucket=settings.GCS_BUCKET,
            use_latest_only=use_latest_only,
        )

        if not paths:
            LOGGER.warning("Skipping %s; no parquet files discovered", mart_name)
            continue

        materialize = mart_name in HOT_MARTS
        sync_strategy = "latest run_date only" if use_latest_only else "all run_dates"
        result = _refresh_mart(
            con=con,
            mart_name=mart_name,
            run_dates=run_dates,
            paths=paths,
            materialize=materialize,
            sync_strategy=sync_strategy,
            dry_run=dry_run,
        )
        results.append(result)
        if not dry_run:
            latest = _latest_run_date(run_dates)
            if not latest and not local_parquet_root:
                latest = marker_date
            if latest:
                marts_state[mart_name] = latest

    if not dry_run:
        state["duckdb_synced_at_utc"] = datetime.now(UTC).isoformat()
        if bigquery_updated_at:
            state["bigquery_updated_at_utc"] = bigquery_updated_at
        try:
            write_sync_state(state, path=SYNC_STATE_PATH)
        except SyncStateUploadError as exc:
            LOGGER.error("%s", exc)
            raise
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
