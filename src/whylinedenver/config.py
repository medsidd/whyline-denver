import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

load_dotenv(override=False)


SERVICE_ACCOUNT_ENV: Final[str] = "GOOGLE_APPLICATION_CREDENTIALS"
SERVICE_ACCOUNT_FILENAME: Final[str] = "whyline-service-account.json"


def _materialize_service_account() -> None:
    """Write inline service-account JSON to disk if provided via env secret."""
    raw = os.getenv(SERVICE_ACCOUNT_ENV)
    if not raw:
        raw_lower = os.getenv(SERVICE_ACCOUNT_ENV.lower())
        if not raw_lower:
            return
        os.environ[SERVICE_ACCOUNT_ENV] = raw_lower
        raw = raw_lower

    if not raw:
        return

    stripped = raw.strip()
    if stripped.startswith("{") and "private_key" in stripped:
        from tempfile import gettempdir

        tmp_root = Path(gettempdir())
        target_dir = tmp_root / "whyline"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / SERVICE_ACCOUNT_FILENAME
        target_path.write_text(stripped, encoding="utf-8")
        os.environ[SERVICE_ACCOUNT_ENV] = str(target_path)
        return

    # Otherwise treat as file path.
    candidate_path = Path(stripped)
    if candidate_path.exists():
        os.environ[SERVICE_ACCOUNT_ENV] = str(candidate_path)
        return

    from tempfile import gettempdir

    tmp_root = Path(gettempdir())
    target_dir = tmp_root / "whyline"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / SERVICE_ACCOUNT_FILENAME
    target_path.write_text(stripped, encoding="utf-8")
    os.environ[SERVICE_ACCOUNT_ENV] = str(target_path)


_materialize_service_account()


@dataclass(frozen=True)
class Settings:
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "whyline-denver")
    GCS_BUCKET: str = os.getenv("GCS_BUCKET", "whylinedenver-raw")
    DUCKDB_GCS_BLOB: str = os.getenv("DUCKDB_GCS_BLOB", "marts/duckdb/warehouse.duckdb")
    DUCKDB_PARQUET_ROOT: str = os.getenv("DUCKDB_PARQUET_ROOT", "data/marts")
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
