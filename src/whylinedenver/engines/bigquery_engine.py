import os
from functools import lru_cache

import pandas as pd
from google.api_core import exceptions
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from whylinedenver.llm import adapt_sql_for_engine
from whylinedenver.semantics.dbt_artifacts import DbtArtifacts


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


def _dry_run_bytes(sql: str) -> int:
    sql = _adapt(sql)
    job = _client().query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=True)
    )
    return job.total_bytes_processed


def estimate(sql: str) -> dict[str, int]:
    return {"bq_est_bytes": _dry_run_bytes(sql)}


def execute(sql: str) -> tuple[dict, pd.DataFrame]:
    sql = _adapt(sql)
    est_bytes = _dry_run_bytes(sql)
    job = _client().query(
        sql,
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=int(os.getenv("MAX_BYTES_BILLED", "2000000000"))
        ),
    )
    results = job.result()
    try:
        df = results.to_dataframe(create_bqstorage_client=True)
    except exceptions.PermissionDenied:
        # Re-execute query since the RowIterator has already been consumed
        job = _client().query(
            sql,
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=int(os.getenv("MAX_BYTES_BILLED", "2000000000"))
            ),
        )
        results = job.result()
        df = results.to_dataframe(create_bqstorage_client=False)
    return {"engine": "bigquery", "rows": len(df), "bq_est_bytes": est_bytes}, df
