from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if SRC_PATH.is_dir():
    src_str = str(SRC_PATH)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


@pytest.fixture(autouse=True)
def _no_cloud_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite offline. With a developer's .env and credentials, the DuckDB refresh tests
    used to overwrite the production warehouse and sync state in GCS."""
    for name in ("SYNC_STATE_GCS_BUCKET", "SYNC_STATE_GCS_REQUIRED", "DUCKDB_GCS_REQUIRED"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("tests must not create real Google Cloud clients")

    from google.cloud import bigquery, storage

    monkeypatch.setattr(storage, "Client", refuse)
    monkeypatch.setattr(bigquery, "Client", refuse)
