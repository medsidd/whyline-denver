from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from whyline.config import Settings
from whyline.sync import refresh_duckdb


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


@pytest.fixture
def multi_run_date_mart_root(tmp_path: Path) -> Path:
    """Create a mart with multiple run_dates to test latest-only logic."""
    root = tmp_path / "marts"
    snapshot_mart = "mart_vulnerability_by_stop"

    # Create 3 run_date partitions with different data
    for _i, run_date in enumerate(["2025-10-20", "2025-10-21", "2025-10-22"], start=1):
        part_dir = root / snapshot_mart / f"run_date={run_date}"
        # Each partition has the same 5 rows (simulating snapshot exports)
        # In reality, only build_run_at would differ
        _write_parquet(part_dir / "part-0.parquet", rows=5)

    return root


def test_latest_run_date_only_prevents_duplicates(
    tmp_path: Path, multi_run_date_mart_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that snapshot marts without time dimensions only read latest run_date."""
    duckdb_path = tmp_path / "warehouse.duckdb"
    state_path = tmp_path / "sync_state.json"

    monkeypatch.setattr(refresh_duckdb, "ALLOWLISTED_MARTS", ("mart_vulnerability_by_stop",))
    monkeypatch.setattr(refresh_duckdb, "HOT_MARTS", set())
    monkeypatch.setattr(
        refresh_duckdb, "LATEST_RUN_DATE_ONLY_MARTS", {"mart_vulnerability_by_stop"}
    )
    monkeypatch.setattr(refresh_duckdb, "SYNC_STATE_PATH", state_path)

    settings = Settings()

    results = refresh_duckdb.refresh(
        settings=settings,
        duckdb_path=duckdb_path,
        local_parquet_root=multi_run_date_mart_root,
        dry_run=False,
    )

    assert len(results) == 1
    assert results[0].mart_name == "mart_vulnerability_by_stop"

    # Should only have 5 rows (from latest run_date), not 15 (from all 3 run_dates)
    con = duckdb.connect(str(duckdb_path))
    row_count = con.execute("SELECT COUNT(*) FROM mart_vulnerability_by_stop").fetchone()[0]
    con.close()

    assert row_count == 5, f"Expected 5 rows (latest only), got {row_count} (indicates duplicates)"

    state = json.loads(state_path.read_text())
    assert state["marts"]["mart_vulnerability_by_stop"] == "2025-10-22"
