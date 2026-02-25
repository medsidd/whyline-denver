# ruff: noqa: I001
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

import duckdb
import pandas as pd

# Conditionally import streamlit for caching
try:
    import streamlit as st

    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


_thread_local = threading.local()
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
    """Ensure a local, fast copy of the DuckDB file exists and return its path.

    If DUCKDB_COPY_LOCAL is not explicitly set to "0", copy the DB file to
    DUCKDB_LOCAL_PATH (default /tmp/warehouse.duckdb) on first access or when
    the source has a newer mtime. Falls back to src if copy fails.
    """
    if os.getenv("DUCKDB_COPY_LOCAL", "1") == "0":
        _logger.debug("DUCKDB_COPY_LOCAL=0, using source path directly: %s", src)
        return src

    default_local = Path(tempfile.gettempdir()) / "warehouse.duckdb"
    dst = Path(os.getenv("DUCKDB_LOCAL_PATH", str(default_local)))
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        needs_copy = True
        if dst.exists() and src.exists():
            # Copy if source is newer or sizes differ
            needs_copy = (src.stat().st_mtime > dst.stat().st_mtime) or (
                src.stat().st_size != dst.stat().st_size
            )
        if needs_copy and src.exists():
            _logger.info("Copying DuckDB from %s to %s", src, dst)
            shutil.copy2(src, dst)
        elif dst.exists():
            _logger.debug("Using existing local DuckDB copy: %s", dst)
        return dst if dst.exists() else src
    except Exception as exc:
        # If anything goes wrong, use the source path
        _logger.warning("Failed to copy DuckDB to local path, using source: %s", exc)
        return src


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


# Streamlit-cached version for long-lived connections
if HAS_STREAMLIT:

    @st.cache_resource
    def _get_cached_connection() -> duckdb.DuckDBPyConnection:
        """Get a cached DuckDB connection (Streamlit only).

        This connection is cached across Streamlit reruns for the lifetime
        of the process, avoiding repeated connection overhead.
        """
        src = _resolve_duckdb_source()
        db_path = _ensure_local_copy(src)
        return _create_connection_internal(db_path)


def _get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection with sane PRAGMAs set.

    - In Streamlit: uses st.cache_resource for process-lifetime caching
    - Otherwise: uses thread-local storage to avoid thread-safety issues
    - Opens database in read-only mode by default
    - Applies conservative resource limits for Cloud Run
    """
    # Use Streamlit cache if available for better performance
    if HAS_STREAMLIT:
        return _get_cached_connection()

    # Fallback to thread-local for non-Streamlit environments
    con = getattr(_thread_local, "con", None)
    if con is not None:
        return con

    src = _resolve_duckdb_source()
    db_path = _ensure_local_copy(src)
    con = _create_connection_internal(db_path)
    _thread_local.con = con
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
