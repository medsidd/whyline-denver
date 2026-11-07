from __future__ import annotations

import os
import shutil
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


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    src = tmp_path / "src" / "warehouse.duckdb"
    src.parent.mkdir()
    base = tmp_path / "local" / "warehouse.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(src))
    monkeypatch.setenv("DUCKDB_LOCAL_PATH", str(base))
    monkeypatch.delenv("DUCKDB_COPY_LOCAL", raising=False)
    monkeypatch.setattr(duckdb_engine, "_RECHECK_SECONDS", 0)
    monkeypatch.setattr(duckdb_engine, "_current_path", None)
    monkeypatch.setattr(duckdb_engine, "_current_checked_at", float("-inf"))
    monkeypatch.setattr(duckdb_engine, "_thread_local", type(duckdb_engine._thread_local)())
    _write_warehouse(src, 1, mtime=1_000_000)
    yield src, base
    con = getattr(duckdb_engine._thread_local, "con", None)
    if con is not None:
        con.close()


def _value() -> int:
    return int(duckdb_engine.execute("SELECT v FROM t")[1]["v"][0])


def test_reopens_when_source_is_refreshed(warehouse: tuple[Path, Path]) -> None:
    src, base = warehouse
    old_con = duckdb_engine._get_connection()
    assert _value() == 1

    _write_warehouse(src, 2, mtime=2_000_000)
    assert _value() == 2
    assert duckdb_engine._get_connection() is not old_con
    size = src.stat().st_size
    assert [p.name for p in base.parent.iterdir()] == [
        f"warehouse-{2_000_000 * 10**9}-{size}.duckdb"
    ]


def test_failed_reopen_keeps_the_old_connection(
    warehouse: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = warehouse
    assert _value() == 1

    _write_warehouse(src, 2, mtime=2_000_000)
    monkeypatch.setattr(duckdb_engine, "_create_connection_internal", _raise)
    with pytest.raises(OSError):
        _value()
    assert int(duckdb_engine._thread_local.con.execute("SELECT v FROM t").fetchone()[0]) == 1


def test_failed_copy_leaves_no_tmp_and_keeps_serving(
    warehouse: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, base = warehouse
    assert _value() == 1
    unrelated = base.parent / "warehouse-backup.duckdb"
    unrelated.write_text("keep me")

    _write_warehouse(src, 2, mtime=2_000_000)

    def partial_copy(_src: Path, dst: Path) -> None:
        Path(dst).write_text("partial")
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", partial_copy)
    assert _value() == 1
    assert not list(base.parent.glob("*.tmp"))
    assert unrelated.exists()


def test_keeps_local_copy_when_source_is_unreadable(warehouse: tuple[Path, Path]) -> None:
    src, _ = warehouse
    copy = duckdb_engine._ensure_local_copy(src)
    src.unlink()
    assert duckdb_engine._ensure_local_copy(src) == copy


def _raise(*_args, **_kwargs):
    raise OSError("cannot open")
