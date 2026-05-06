"""Shared constants for sync utilities."""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class MartEntry:
    name: str
    layer: Literal["dim", "fct", "agg", "mart"]
    bq_dataset: Literal["stg", "mart"]  # logical key; resolved via Settings at runtime
    _: KW_ONLY
    allow_prompt: bool  # included in LLM schema brief
    allow_sql: bool  # accepted by SQL guardrails and BQ qualification map
    allow_download: bool  # visible in /api/downloads/options
    download_label: str  # human-readable label; empty string if not downloadable
    sync_to_duckdb: bool  # included in DuckDB refresh
    export_to_gcs: bool  # exported to GCS parquet
    duckdb_hot: (
        bool  # materialized as DuckDB table (vs view); only meaningful if sync_to_duckdb=True
    )
    latest_only: (
        bool  # export only the latest run_date partition; only meaningful if export_to_gcs=True
    )
    partition_column: Optional[str] = None
    export_geom: bool = False
    deprecated: bool = False  # compat view; allow_sql=True; absent from brief and downloads


def resolve_bq_dataset(entry: MartEntry, settings) -> str:
    return settings.BQ_DATASET_STG if entry.bq_dataset == "stg" else settings.BQ_DATASET_MART


MART_REGISTRY: list[MartEntry] = [
    # --- Dimensions (logical dataset: stg_denver) ---
    MartEntry(
        "dim_stop",
        "dim",
        "stg",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Stops reference",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "dim_route",
        "dim",
        "stg",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Routes reference",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "dim_date",
        "dim",
        "stg",
        allow_prompt=True,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "dim_weather",
        "dim",
        "stg",
        allow_prompt=True,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    # dim_census_tract: BigQuery-only (spatial joins at mart build time); not in DuckDB or GCS
    MartEntry(
        "dim_census_tract",
        "dim",
        "stg",
        allow_prompt=False,
        allow_sql=False,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    # --- Facts (BigQuery-only; too large for DuckDB; allow_sql=False so LLM cannot query) ---
    MartEntry(
        "fct_transit_events",
        "fct",
        "stg",
        allow_prompt=False,
        allow_sql=False,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
        partition_column="service_date_mst",
    ),
    MartEntry(
        "fct_headway_adherence",
        "fct",
        "stg",
        allow_prompt=False,
        allow_sql=False,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
        partition_column="service_date_mst",
    ),
    # --- Aggregates (logical dataset: mart_denver) ---
    MartEntry(
        "agg_reliability_by_route_day",
        "agg",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Reliability by route & day",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=False,
        partition_column="service_date_mst",
    ),
    MartEntry(
        "agg_reliability_by_stop_hour",
        "agg",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Reliability by stop & hour",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=False,
        partition_column="service_date_mst",
    ),
    MartEntry(
        "agg_weather_impacts_by_route",
        "agg",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Weather impacts by route",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    # --- Marts (logical dataset: mart_denver) ---
    MartEntry(
        "mart_stop_reliability_score",
        "mart",
        "mart",
        allow_prompt=False,
        allow_sql=False,
        allow_download=False,
        download_label="",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "mart_stop_safety",
        "mart",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Stop safety scores",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "mart_stop_access",
        "mart",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Stop access scores",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "mart_stop_equity",
        "mart",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Stop equity scores",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    MartEntry(
        "mart_stop_priority",
        "mart",
        "mart",
        allow_prompt=True,
        allow_sql=True,
        allow_download=True,
        download_label="Stop priority ranking",
        sync_to_duckdb=True,
        export_to_gcs=True,
        duckdb_hot=True,
        latest_only=True,
    ),
    # --- Deprecated compat views (bq_dataset="mart": live in mart_denver dataset) ---
    # export_to_gcs=False on all deprecated entries → latest_only=False (invariant)
    MartEntry(
        "mart_gtfs_stops",
        "dim",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_gtfs_routes",
        "dim",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_reliability_by_route_day",
        "agg",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_reliability_by_stop_hour",
        "agg",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_weather_impacts",
        "agg",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_crash_proximity_by_stop",
        "mart",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_access_score_by_stop",
        "mart",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_vulnerability_by_stop",
        "mart",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
    MartEntry(
        "mart_priority_hotspots",
        "mart",
        "mart",
        deprecated=True,
        allow_prompt=False,
        allow_sql=True,
        allow_download=False,
        download_label="",
        sync_to_duckdb=False,
        export_to_gcs=False,
        duckdb_hot=False,
        latest_only=False,
    ),
]

MART_BY_NAME: dict[str, MartEntry] = {e.name: e for e in MART_REGISTRY}

# ── Phases 1–4: ALLOWLISTED_MARTS stays as the hardcoded 9-name tuple so the API
#    layer (guardrails, schema brief, /api/models) sees only the current marts.
#    MART_BY_NAME is the only new export used during these phases.
#
# ── Phase 5 (API cutover): replace the hardcoded tuple below with:
#    ALLOWLISTED_MARTS = GUARDRAIL_MARTS
#    and add the derived constants block that follows.

PROMPT_MARTS: tuple[str, ...] = tuple(e.name for e in MART_REGISTRY if e.allow_prompt)
GUARDRAIL_MARTS: tuple[str, ...] = tuple(e.name for e in MART_REGISTRY if e.allow_sql)
DOWNLOAD_MARTS: tuple[str, ...] = tuple(
    e.name for e in MART_REGISTRY if e.allow_download and not e.deprecated
)
EXPORT_MARTS: tuple[str, ...] = tuple(e.name for e in MART_REGISTRY if e.export_to_gcs)
SYNC_MARTS: tuple[str, ...] = tuple(e.name for e in MART_REGISTRY if e.sync_to_duckdb)
ALLOWLISTED_MARTS: tuple[str, ...] = GUARDRAIL_MARTS
HOT_MARTS: frozenset[str] = frozenset(
    e.name for e in MART_REGISTRY if e.duckdb_hot and e.sync_to_duckdb
)
LATEST_RUN_DATE_ONLY: frozenset[str] = frozenset(
    e.name for e in MART_REGISTRY if e.latest_only and e.export_to_gcs
)
PARTITIONED_MARTS: frozenset[str] = frozenset(
    e.name for e in MART_REGISTRY if e.partition_column and e.export_to_gcs
)

__all__ = [
    "ALLOWLISTED_MARTS",
    "DOWNLOAD_MARTS",
    "EXPORT_MARTS",
    "GUARDRAIL_MARTS",
    "HOT_MARTS",
    "LATEST_RUN_DATE_ONLY",
    "MART_BY_NAME",
    "MART_REGISTRY",
    "MartEntry",
    "PARTITIONED_MARTS",
    "PROMPT_MARTS",
    "SYNC_MARTS",
    "resolve_bq_dataset",
]
