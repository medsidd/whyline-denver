from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from whylinedenver.config import Settings
from whylinedenver.sync import refresh_duckdb


def _write_parquet(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT range AS value FROM range({rows})) " f"TO '{path}' (FORMAT 'parquet')"
    )
    con.close()


@pytest.fixture
def local_mart_root(tmp_path: Path) -> Path:
    root = tmp_path / "marts"
    hot_dir = root / "mart_hot" / "run_date=2025-10-22"
    cold_dir = root / "mart_cold" / "run_date=2025-10-23"
    _write_parquet(hot_dir / "part-0.parquet", rows=3)
    _write_parquet(cold_dir / "part-0.parquet", rows=2)
    return root


def test_refresh_creates_tables_and_views(
    tmp_path: Path, local_mart_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duckdb_path = tmp_path / "warehouse.duckdb"
    state_path = tmp_path / "sync_state.json"

    monkeypatch.setattr(refresh_duckdb, "ALLOWLISTED_MARTS", ("mart_hot", "mart_cold"))
    monkeypatch.setattr(refresh_duckdb, "HOT_MARTS", {"mart_hot"})
    monkeypatch.setattr(refresh_duckdb, "SYNC_STATE_PATH", state_path)

    settings = Settings()

    results = refresh_duckdb.refresh(
        settings=settings,
        duckdb_path=duckdb_path,
        local_parquet_root=local_mart_root,
        dry_run=False,
    )

    assert {r.mart_name for r in results} == {"mart_hot", "mart_cold"}

    con = duckdb.connect(str(duckdb_path))
    assert con.execute("SELECT COUNT(*) FROM mart_hot").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM mart_cold").fetchone()[0] == 2
    con.close()

    state = json.loads(state_path.read_text())
    assert state["marts"]["mart_hot"] == "2025-10-22"
    assert state["marts"]["mart_cold"] == "2025-10-23"
