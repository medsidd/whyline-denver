# ruff: noqa: I001
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from whyline.sql_guardrails import SqlValidationError

_thread_local = threading.local()
# The local copy every thread should use, rechecked against the source at most once a minute.
_current_lock = threading.Lock()
_current_path: Path | None = None
_current_checked_at = float("-inf")
_RECHECK_SECONDS = 60
_logger = logging.getLogger(__name__)


def _resolve_duckdb_source() -> Path:
    """Return the configured DuckDB source path.

    Honors DUCKDB_PATH and falls back to data/warehouse.duckdb relative to repo root.
    """
    env_path = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
    path = Path(env_path).expanduser()
    if not path.is_absolute():
        # Resolve relative to project root (two levels up from this file)
        root = Path(__file__).resolve().parents[3]
        path = (root / path).resolve()

    _logger.info("Resolved DuckDB path: %s (exists=%s)", path, path.exists())
    if not path.exists():
        _logger.warning("DuckDB file not found at %s", path)

    return path


def _local_copies(base: Path) -> list[Path]:
    """Copies made by _ensure_local_copy, oldest first."""
    pattern = re.compile(rf"{re.escape(base.stem)}-(\d+)-\d+{re.escape(base.suffix)}")
    found = [(m, p) for p in base.parent.glob("*") if (m := pattern.fullmatch(p.name))]
    return [p for m, p in sorted(found, key=lambda item: int(item[0].group(1)))]


def _ensure_local_copy(src: Path) -> Path:
    """Ensure a local, fast copy of the current DuckDB file exists and return its path.

    If DUCKDB_COPY_LOCAL is not explicitly set to "0", copy the DB file next to
    DUCKDB_LOCAL_PATH (default /tmp/warehouse.duckdb) under a name that carries the
    source version, warehouse-<mtime_ns>-<size>.duckdb. A refreshed source gets a new
    file, so connections open on the old copy keep working until they reopen, and
    DuckDB's per-path instance cache cannot hand back the old database. If the copy
    fails, falls back to the newest local copy, then to src.
    """
    if os.getenv("DUCKDB_COPY_LOCAL", "1") == "0":
        _logger.debug("DUCKDB_COPY_LOCAL=0, using source path directly: %s", src)
        return src

    default_local = Path(tempfile.gettempdir()) / "warehouse.duckdb"
    base = Path(os.getenv("DUCKDB_LOCAL_PATH", str(default_local)))
    try:
        stat = src.stat()
        dst = base.with_name(f"{base.stem}-{stat.st_mtime_ns}-{stat.st_size}{base.suffix}")
        if not dst.exists():
            _logger.info("Copying DuckDB from %s to %s", src, dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
            try:
                shutil.copy2(src, tmp)
                os.replace(tmp, dst)
            finally:
                tmp.unlink(missing_ok=True)
            # Open connections keep their unlinked file; /tmp on Cloud Run is memory.
            for old in _local_copies(base):
                if old != dst:
                    old.unlink(missing_ok=True)
        return dst
    except Exception as exc:
        # Keep serving the newest local copy if the source is briefly unreadable
        copies = _local_copies(base)
        fallback = copies[-1] if copies else src
        _logger.warning("Failed to copy DuckDB to local path, using %s: %s", fallback, exc)
        return fallback


def _current_db_path() -> Path:
    """Return the database every thread should use, checking the source at most once a minute.

    One thread does the check and any copy; the others keep the current path meanwhile.
    """
    global _current_path, _current_checked_at
    fresh = time.monotonic() - _current_checked_at < _RECHECK_SECONDS
    if _current_path is not None and fresh:
        return _current_path
    if not _current_lock.acquire(blocking=_current_path is None):
        return _current_path
    try:
        if _current_path is None or time.monotonic() - _current_checked_at >= _RECHECK_SECONDS:
            _current_path = _ensure_local_copy(_resolve_duckdb_source())
            _current_checked_at = time.monotonic()
        return _current_path
    finally:
        _current_lock.release()


def _create_connection_internal(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a new DuckDB connection with configured PRAGMAs.

    This is the actual connection creation logic, separated for caching.
    """
    read_only_env = os.getenv("DUCKDB_READ_ONLY", "1")
    read_only = read_only_env not in {"0", "false", "False"}

    _logger.info("Opening DuckDB connection: path=%s, read_only=%s", db_path, read_only)
    con = duckdb.connect(database=str(db_path), read_only=read_only)

    # Apply PRAGMAs. Allow overrides via env vars.
    threads = int(os.getenv("DUCKDB_THREADS", "2"))
    mem_limit = os.getenv("DUCKDB_MEMORY_LIMIT", "1GB")
    # A folder of its own: with external access off, SQL can still read files inside the
    # temp directory, and /tmp holds more than DuckDB's spill files.
    temp_dir = Path(os.getenv("DUCKDB_TEMP_DIR", tempfile.gettempdir())) / "duckdb-spill"
    pragmas = [
        f"PRAGMA threads={threads};",
        f"PRAGMA memory_limit='{mem_limit}';",
        f"PRAGMA temp_directory='{temp_dir}';",
        "PRAGMA enable_progress_bar=false;",
    ]
    for stmt in pragmas:
        try:
            con.execute(stmt)
        except duckdb.Error as exc:
            # Pragmas are best-effort; continue on failure
            _logger.debug("DuckDB PRAGMA failed: %s (%s)", stmt, exc)

    # Read-only protects the database, not the disk: without this, visitor SQL can call
    # read_text('/proc/self/environ'). Not best-effort; a failure here must stop the query.
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    return con


def _get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection with sane PRAGMAs set.

    Uses thread-local storage to avoid thread-safety issues. Opens database
    in read-only mode by default and applies conservative resource limits
    for Cloud Run. Reopens when _current_db_path moves to a newer copy, so
    warm instances pick up the nightly refresh.
    """
    db_path = _current_db_path()
    con = getattr(_thread_local, "con", None)
    if con is not None and _thread_local.path == db_path:
        return con

    new_con = _create_connection_internal(db_path)
    _thread_local.con = new_con
    _thread_local.path = db_path
    if con is not None:
        con.close()
    return new_con


def _check_reads(con: duckdb.DuckDBPyConnection, sql: str, allowed_tables: Iterable[str]) -> None:
    """Refuse anything but one SELECT over the allowed tables, as DuckDB itself parses it.

    The text checks in sql_guardrails can be talked around (comma joins, comments, TABLE x);
    DuckDB's own statement type and table list cannot.
    """
    try:
        statements = duckdb.extract_statements(sql)
        tables = con.get_table_names(sql)
    except duckdb.Error as exc:
        raise SqlValidationError(f"The SQL could not be parsed: {exc}") from exc
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise SqlValidationError("Only single SELECT statements are allowed.")
    allowed = {name.lower() for name in allowed_tables}
    bad = sorted(name for name in tables if name.lower() not in allowed)
    if bad:
        raise SqlValidationError(
            f"Query references unauthorized tables: {', '.join(bad)}. "
            "Only app-approved marts may be queried."
        )


def execute(
    sql: str, *, allowed_tables: Iterable[str] | None = None, max_rows: int | None = None
) -> tuple[dict, pd.DataFrame]:
    """Execute SQL query and return stats and results DataFrame.

    Visitor SQL passes `allowed_tables` (checked with DuckDB's parser) and `max_rows`
    (rows fetched; `truncated` in the stats says whether more were left behind).
    """
    try:
        con = _get_connection()
        if allowed_tables is not None:
            _check_reads(con, sql, allowed_tables)
        _logger.debug("Executing query: %s", sql[:200])  # Log first 200 chars
        cursor = con.execute(sql)
        if max_rows is None:
            df = cursor.fetch_df()
            truncated = False
        else:
            # Chunks hold 2,048 rows each; ask for enough to see one row past the cap
            df = cursor.fetch_df_chunk(max_rows // 2048 + 1)
            truncated = len(df) > max_rows
            df = df.head(max_rows)
        stats = {"engine": "duckdb", "rows": len(df), "total_rows": len(df), "truncated": truncated}
        _logger.info("Query executed successfully: %d rows", len(df))
        return stats, df
    except SqlValidationError:
        raise
    except Exception as exc:
        _logger.error("DuckDB query failed: %s", exc, exc_info=True)
        raise
