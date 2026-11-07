from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from whyline.engines import duckdb_engine


def _write_warehouse(path: Path, value: int, mtime: int) -> None:
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute(f"CREATE TABLE t AS SELECT {value} AS v")
    con.close()
    os.utime(path, (mtime, mtime))


def test_reopens_when_source_is_refreshed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src" / "warehouse.duckdb"
    src.parent.mkdir()
    local = tmp_path / "local" / "warehouse.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(src))
    monkeypatch.setenv("DUCKDB_LOCAL_PATH", str(local))
    monkeypatch.delenv("DUCKDB_COPY_LOCAL", raising=False)
    monkeypatch.setattr(duckdb_engine, "_RECHECK_SECONDS", 0)
    monkeypatch.setattr(duckdb_engine, "_thread_local", type(duckdb_engine._thread_local)())

    _write_warehouse(src, 1, mtime=1_000_000)
    old_con = duckdb_engine._get_connection()
    assert duckdb_engine.execute("SELECT v FROM t")[1]["v"].tolist() == [1]

    _write_warehouse(src, 2, mtime=2_000_000)
    assert duckdb_engine.execute("SELECT v FROM t")[1]["v"].tolist() == [2]
    assert duckdb_engine._get_connection() is not old_con
    assert [p.name for p in local.parent.iterdir()] == [f"warehouse-{2_000_000 * 10**9}.duckdb"]

    duckdb_engine._get_connection().close()


def test_keeps_local_copy_when_source_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "warehouse.duckdb"
    base = tmp_path / "local" / "warehouse.duckdb"
    monkeypatch.setenv("DUCKDB_LOCAL_PATH", str(base))
    monkeypatch.delenv("DUCKDB_COPY_LOCAL", raising=False)

    _write_warehouse(src, 1, mtime=1_000_000)
    copy = duckdb_engine._ensure_local_copy(src)
    src.unlink()
    assert duckdb_engine._ensure_local_copy(src) == copy
