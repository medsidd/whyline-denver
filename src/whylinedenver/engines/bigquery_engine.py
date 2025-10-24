import os

import pandas as pd
from google.cloud import bigquery

client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))


def _dry_run_bytes(sql: str) -> int:
    job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=True))
    return job.total_bytes_processed


def estimate(sql: str) -> dict[str, int]:
    return {"bq_est_bytes": _dry_run_bytes(sql)}


def execute(sql: str) -> tuple[dict, pd.DataFrame]:
    est_bytes = _dry_run_bytes(sql)
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=int(os.getenv("MAX_BYTES_BILLED", "2000000000"))
        ),
    )
    df = job.result().to_dataframe(create_bqstorage_client=True)
    return {"engine": "bigquery", "rows": len(df), "bq_est_bytes": est_bytes}, df
