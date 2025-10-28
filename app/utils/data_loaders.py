"""Data loading utilities for populating filter widgets."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Add src to path for imports
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from whylinedenver.config import settings
from whylinedenver.engines import bigquery_engine, duckdb_engine
from whylinedenver.llm import adapt_sql_for_engine
from whylinedenver.semantics.dbt_artifacts import DbtArtifacts, ModelInfo
from whylinedenver.sync.state_store import load_sync_state

from .formatting import format_timestamp


@st.cache_data
def load_allowed_models() -> dict[str, ModelInfo]:
    """Load allowed dbt models from artifacts."""
    artifacts = DbtArtifacts()
    return artifacts.allowed_models()


@st.cache_data
def load_route_options(engine_name: str) -> tuple[list[str], str | None]:
    """Load route options from the selected engine. Returns (routes, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        sql = (
            f"SELECT DISTINCT route_id FROM {table_name} "
            "WHERE route_id IS NOT NULL ORDER BY route_id LIMIT 200"
        )
        models = load_allowed_models()
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine_module.execute(sql)
        return df["route_id"].astype(str).tolist(), None
    except Exception as exc:
        return [], str(exc)


@st.cache_data
def load_stop_lookup(engine_name: str) -> pd.DataFrame:
    """Return stop metadata (id, name, lat/lon) for tooltips and charts."""
    if engine_name != "bigquery":
        return pd.DataFrame(columns=["stop_id", "stop_name", "stop_lat", "stop_lon"])

    try:
        engine_module = bigquery_engine
        table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_STG}.stg_gtfs_stops`"

        sql = f"SELECT stop_id, stop_name, stop_lat, stop_lon " f"FROM {table_name}"
        models = load_allowed_models()
        sql = adapt_sql_for_engine(sql, engine_name, models)

        _, df = engine_module.execute(sql)
        for col in ("stop_id",):
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df
    except Exception as exc:
        return pd.DataFrame(columns=["stop_id", "stop_name", "stop_lat", "stop_lon"]).assign(
            error=str(exc)
        )


@st.cache_data
def load_weather_bins(engine_name: str) -> tuple[list[str], str | None]:
    """Load weather bins from the selected engine. Returns (bins, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        sql = (
            f"SELECT DISTINCT precip_bin FROM {table_name} "
            "WHERE precip_bin IS NOT NULL ORDER BY precip_bin"
        )
        models = load_allowed_models()
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine_module.execute(sql)
        return df["precip_bin"].astype(str).tolist(), None
    except Exception as exc:
        return ["none", "rain", "snow"], str(exc)


@st.cache_data
def load_service_date_range(engine_name: str) -> tuple[date | None, date | None, str | None]:
    """Load service date range from the selected engine. Returns (min_date, max_date, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        sql = (
            f"SELECT MIN(service_date_mst) AS min_date, MAX(service_date_mst) AS max_date "
            f"FROM {table_name}"
        )
        models = load_allowed_models()
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine_module.execute(sql)
        if df.empty:
            return None, None, "No data found in mart_reliability_by_route_day"
        min_timestamp = pd.to_datetime(df.loc[0, "min_date"])
        max_timestamp = pd.to_datetime(df.loc[0, "max_date"])
        if pd.isna(min_timestamp) or pd.isna(max_timestamp):
            return None, None, "Date values are null or invalid"
        min_date = min_timestamp.date()
        max_date = max_timestamp.date()
        return min_date, max_date, None
    except Exception as exc:
        return None, None, str(exc)


@st.cache_data(ttl=60)
def _load_sync_state_payload() -> dict[str, Any] | None:
    """Load sync_state with a short cache to avoid repeated GCS reads."""
    return load_sync_state()


def read_duckdb_freshness() -> str:
    """Read DuckDB sync timestamp from sync_state.json (preferring GCS)."""
    payload = _load_sync_state_payload()
    if not payload:
        return "Unavailable"
    ts = payload.get("duckdb_synced_at_utc") or payload.get("refreshed_at_utc")  # Backward compat
    if ts:
        return format_timestamp(ts)

    marts = payload.get("marts")
    if isinstance(marts, dict) and marts:
        latest = max(marts.values())
        return f"Latest run_date {latest}"

    return "Awaiting first DuckDB sync"


def read_bigquery_freshness() -> str:
    """Read BigQuery update timestamp from sync_state.json."""
    payload = _load_sync_state_payload()
    if payload:
        ts = payload.get("bigquery_updated_at_utc")
        if ts:
            return format_timestamp(ts)

    try:
        # Fallback: read from dbt run_results.json if not in sync_state
        dbt_path = Path("dbt/target/run_results.json")
        if dbt_path.exists():
            dbt_payload = json.loads(dbt_path.read_text(encoding="utf-8"))
            metadata = dbt_payload.get("metadata", {})
            generated_at = metadata.get("generated_at")
            if generated_at:
                return format_timestamp(generated_at)

        return "Unavailable"
    except (json.JSONDecodeError, OSError, ValueError):
        return "Unavailable"
