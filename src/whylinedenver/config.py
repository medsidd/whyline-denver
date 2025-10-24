import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "whyline-denver")
    GCS_BUCKET: str = os.getenv("GCS_BUCKET", "whylinedenver-raw")
    BQ_DATASET_RAW: str = os.getenv("BQ_DATASET_RAW", "raw_denver")
    BQ_DATASET_STG: str = os.getenv("BQ_DATASET_STG", "stg_denver")
    BQ_DATASET_MART: str = os.getenv("BQ_DATASET_MART", "mart_denver")
    ENGINE: str = os.getenv("ENGINE", "duckdb")  # duckdb|bigquery
    DBT_TARGET: str = os.getenv("DBT_TARGET", "prod")
    MAX_BYTES_BILLED: int = int(os.getenv("MAX_BYTES_BILLED", "2000000000"))  # 2GB
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    def validate(self) -> None:
        # Minimal checks; more later by phase
        if self.ENGINE not in ("duckdb", "bigquery"):
            raise ValueError("ENGINE must be duckdb or bigquery")


settings = Settings()
settings.validate()
