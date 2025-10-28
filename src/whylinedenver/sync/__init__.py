"""
Synchronization helpers for moving marts between BigQuery, GCS, and DuckDB.

Available entrypoints:
- `export_bq_marts_main`: export marts from BigQuery to Parquet in GCS.
- `refresh_duckdb_main`: hydrate DuckDB tables/views from the exported Parquet.
"""

from __future__ import annotations

from .constants import ALLOWLISTED_MARTS


def _export_bq_module():
    from . import export_bq_marts as _module

    return _module


def export_bq_marts_main(*args, **kwargs):
    """Delegate to ``export_bq_marts.main`` without eager submodule import."""
    return _export_bq_module().main(*args, **kwargs)


def get_allowlisted_marts() -> tuple[str, ...]:
    """Expose the allow-listed marts tuple."""
    return ALLOWLISTED_MARTS


def refresh_duckdb_main(*args, **kwargs):
    """Import lazily to avoid double-import warnings when run as a module."""
    from .refresh_duckdb import main as _refresh_duckdb_main

    return _refresh_duckdb_main(*args, **kwargs)


__all__ = ["ALLOWLISTED_MARTS", "export_bq_marts_main", "refresh_duckdb_main"]
