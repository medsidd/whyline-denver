import os

import pandas as pd
from google.cloud import bigquery


def execute(sql: str) -> tuple[dict, pd.DataFrame]:
    client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))
    job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=True))
    est_bytes = job.total_bytes_processed
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=int(os.getenv("MAX_BYTES_BILLED", "2000000000"))
        ),
    )
    df = job.result().to_dataframe(create_bqstorage_client=True)
    return {"engine": "bigquery", "rows": len(df), "bq_est_bytes": est_bytes}, df
