import os
from functools import lru_cache
from typing import Iterable

import pandas as pd
from google.api_core import exceptions
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from whyline.config import settings
from whyline.llm import adapt_sql_for_engine
from whyline.semantics.dbt_artifacts import DbtArtifacts
from whyline.sql_guardrails import SqlValidationError
from whyline.sync.constants import LIVE_MARTS

# Cloud Run cuts a request off at 300 s; stop the query first so it doesn't keep billing.
JOB_TIMEOUT_MS = 120_000


@lru_cache(maxsize=1)
def _client() -> bigquery.Client:
    project = os.getenv("GCP_PROJECT_ID")
    try:
        return bigquery.Client(project=project)
    except DefaultCredentialsError as exc:  # pragma: no cover - requires external ADC setup
        raise RuntimeError(
            "BigQuery credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "gcloud auth application-default login before using the BigQuery engine."
        ) from exc


@lru_cache(maxsize=1)
def _allowed_models():
    return DbtArtifacts().allowed_models()


def _adapt(sql: str) -> str:
    return adapt_sql_for_engine(sql, "bigquery", _allowed_models())


def _dry_run(sql: str) -> bigquery.QueryJob:
    return _client().query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=True)
    )


def _table_key(table) -> tuple[str, str, str]:
    return (table.project.lower(), table.dataset_id.lower(), table.table_id.lower())


@lru_cache(maxsize=1)
def _live_view_tables() -> frozenset[tuple[str, str, str]]:
    """The base tables behind the live views; a dry run reports those, not the view."""
    found: set[tuple[str, str, str]] = set()
    for name in LIVE_MARTS:
        view = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{name}`"
        found.update(_table_key(t) for t in _dry_run(f"SELECT * FROM {view}").referenced_tables)
    return frozenset(found)


def _check_reads(job: bigquery.QueryJob, allowed_tables: Iterable[str]) -> None:
    """Refuse anything but one SELECT over the allowed marts, as BigQuery itself parsed it.

    The text checks in sql_guardrails can be talked around (comma joins, comments); the
    dry run's statement type and table list cannot.
    """
    if job.statement_type != "SELECT":
        raise SqlValidationError("Only single SELECT statements are allowed.")
    allowed = {name.lower() for name in allowed_tables}
    project = (settings.GCP_PROJECT_ID or "").lower()
    dataset = (settings.BQ_DATASET_MART or "").lower()

    def outside(live: frozenset[tuple[str, str, str]]) -> list[str]:
        return sorted(
            ".".join(key)
            for key in map(_table_key, job.referenced_tables)
            if not (key[:2] == (project, dataset) and key[2] in allowed) and key not in live
        )

    reads_live = any(name in allowed for name in LIVE_MARTS)
    bad = outside(_live_view_tables() if reads_live else frozenset())
    if bad and reads_live:
        # A live view may have been redefined since this process cached its base tables
        _live_view_tables.cache_clear()
        bad = outside(_live_view_tables())
    if bad:
        raise SqlValidationError(
            f"Query references unauthorized tables: {', '.join(bad)}. "
            "Only app-approved marts may be queried."
        )


def estimate(sql: str, *, allowed_tables: Iterable[str] | None = None) -> dict[str, int]:
    job = _dry_run(_adapt(sql))
    if allowed_tables is not None:
        _check_reads(job, allowed_tables)
    return {"bq_est_bytes": job.total_bytes_processed}


def execute(
    sql: str, *, allowed_tables: Iterable[str] | None = None, max_rows: int | None = None
) -> tuple[dict, pd.DataFrame]:
    """Run a query. Visitor SQL passes `allowed_tables` (checked against the dry run) and
    `max_rows` (rows fetched; `total_rows` in the stats is still the full count)."""
    sql = _adapt(sql)
    dry = _dry_run(sql)
    if allowed_tables is not None:
        _check_reads(dry, allowed_tables)
    config = bigquery.QueryJobConfig(
        maximum_bytes_billed=int(os.getenv("MAX_BYTES_BILLED", "2000000000")),
        job_timeout_ms=JOB_TIMEOUT_MS,
    )
    results = _client().query(sql, job_config=config).result(max_results=max_rows)
    total_rows = results.total_rows
    try:
        # The Storage API reads whole results only; a capped read goes through REST
        df = results.to_dataframe(create_bqstorage_client=max_rows is None)
    except exceptions.PermissionDenied:
        # Re-execute query since the RowIterator has already been consumed
        results = _client().query(sql, job_config=config).result(max_results=max_rows)
        df = results.to_dataframe(create_bqstorage_client=False)
    stats = {
        "engine": "bigquery",
        "rows": len(df),
        "total_rows": total_rows if total_rows is not None else len(df),
        "bq_est_bytes": dry.total_bytes_processed,
    }
    return stats, df
