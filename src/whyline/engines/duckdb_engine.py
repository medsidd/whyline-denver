# ruff: noqa: I001
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import duckdb
import pandas as pd

_thread_local = threading.local()
_copy_lock = threading.Lock()
# How often each thread checks the source for a newer warehouse.
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


def _ensure_local_copy(src: Path) -> Path:
    """Ensure a local, fast copy of the current DuckDB file exists and return its path.

    If DUCKDB_COPY_LOCAL is not explicitly set to "0", copy the DB file next to
    DUCKDB_LOCAL_PATH (default /tmp/warehouse.duckdb) under a name that carries the
    source mtime, e.g. warehouse-<mtime_ns>.duckdb. A refreshed source gets a new
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
        dst = base.with_name(f"{base.stem}-{src.stat().st_mtime_ns}{base.suffix}")
        with _copy_lock:
            if not dst.exists():
                _logger.info("Copying DuckDB from %s to %s", src, dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
                shutil.copy2(src, tmp)
                os.replace(tmp, dst)
                # Open connections keep their unlinked file; /tmp on Cloud Run is memory.
                for old in base.parent.glob(f"{base.stem}-*"):
                    if old != dst:
                        old.unlink(missing_ok=True)
        return dst
    except Exception as exc:
        # Keep serving the newest local copy if the source is briefly unreadable
        copies = sorted(base.parent.glob(f"{base.stem}-*{base.suffix}"))
        fallback = copies[-1] if copies else src
        _logger.warning("Failed to copy DuckDB to local path, using %s: %s", fallback, exc)
        return fallback


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
    temp_dir = os.getenv("DUCKDB_TEMP_DIR", tempfile.gettempdir())
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

    return con


def _get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection with sane PRAGMAs set.

    Uses thread-local storage to avoid thread-safety issues. Opens database
    in read-only mode by default and applies conservative resource limits
    for Cloud Run. Every _RECHECK_SECONDS it checks the source and reopens
    on a newer copy, so warm instances pick up the nightly refresh.
    """
    con = getattr(_thread_local, "con", None)
    if con is not None and time.monotonic() - _thread_local.checked_at < _RECHECK_SECONDS:
        return con

    db_path = _ensure_local_copy(_resolve_duckdb_source())
    _thread_local.checked_at = time.monotonic()
    if con is not None and _thread_local.path == db_path:
        return con

    if con is not None:
        con.close()
    con = _create_connection_internal(db_path)
    _thread_local.con = con
    _thread_local.path = db_path
    return con


def execute(sql: str) -> tuple[dict, pd.DataFrame]:
    """Execute SQL query and return stats and results DataFrame."""
    try:
        con = _get_connection()
        _logger.debug("Executing query: %s", sql[:200])  # Log first 200 chars
        df = con.execute(sql).fetch_df()
        stats = {"engine": "duckdb", "rows": len(df)}
        _logger.info("Query executed successfully: %d rows", len(df))
        return stats, df
    except Exception as exc:
        _logger.error("DuckDB query failed: %s", exc, exc_info=True)
        raise
