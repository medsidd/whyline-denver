"""Filter data endpoints — routes, weather bins, date range, stops, models."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_models
from api.models import FilterOptionsResponse, ModelColumnInfo, ModelInfo, ModelsResponse
from whyline.config import settings
from whyline.engines import bigquery_engine, duckdb_engine
from whyline.llm import adapt_sql_for_engine

router = APIRouter()


def _engine_module(engine_name: str):
    return duckdb_engine if engine_name == "duckdb" else bigquery_engine


def _qualify_table(engine_name: str, table: str) -> str:
    if engine_name == "bigquery":
        return f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{table}`"
    return table


def _qualify_stg_table(engine_name: str, table: str) -> str:
    if engine_name == "bigquery":
        return f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_STG}.{table}`"
    return table


@router.get("/filters/{engine_name}", response_model=FilterOptionsResponse)
def get_filters(engine_name: str) -> FilterOptionsResponse:
    """Return routes, weather bins, and date range for the selected engine."""
    if engine_name not in ("duckdb", "bigquery"):
        raise HTTPException(status_code=400, detail="engine must be 'duckdb' or 'bigquery'")

    models = get_models()
    engine = _engine_module(engine_name)
    table = _qualify_table(engine_name, "mart_reliability_by_route_day")

    # Routes
    routes: list[str] = []
    error: str | None = None
    try:
        sql = (
            f"SELECT DISTINCT route_id FROM {table} "
            "WHERE route_id IS NOT NULL ORDER BY route_id LIMIT 200"
        )
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine.execute(sql)
        routes = df["route_id"].astype(str).tolist()
    except Exception as exc:
        error = str(exc)

    # Weather bins
    weather_bins: list[str] = ["none", "rain", "snow"]
    try:
        sql = (
            f"SELECT DISTINCT precip_bin FROM {table} "
            "WHERE precip_bin IS NOT NULL ORDER BY precip_bin"
        )
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine.execute(sql)
        weather_bins = df["precip_bin"].astype(str).tolist()
    except Exception:
        pass  # use defaults

    # Date range
    date_min: str | None = None
    date_max: str | None = None
    try:
        sql = (
            f"SELECT MIN(service_date_mst) AS min_date, MAX(service_date_mst) AS max_date "
            f"FROM {table}"
        )
        if engine_name == "bigquery":
            sql = adapt_sql_for_engine(sql, engine_name, models)
        _, df = engine.execute(sql)
        if not df.empty:
            min_ts = pd.to_datetime(df.loc[0, "min_date"])
            max_ts = pd.to_datetime(df.loc[0, "max_date"])
            if pd.notna(min_ts) and pd.notna(max_ts):
                date_min = min_ts.date().isoformat()
                date_max = max_ts.date().isoformat()
    except Exception:
        pass

    return FilterOptionsResponse(
        routes=routes,
        weather_bins=weather_bins,
        date_min=date_min,
        date_max=date_max,
        error=error,
    )


@router.get("/filters/{engine_name}/stops")
def get_stops(engine_name: str) -> list[dict]:
    """Return stop lookup table (id, name, lat, lon). BigQuery only."""
    if engine_name != "bigquery":
        return []

    models = get_models()
    table = _qualify_stg_table(engine_name, "stg_gtfs_stops")
    sql = f"SELECT stop_id, stop_name, stop_lat, stop_lon FROM {table}"
    sql = adapt_sql_for_engine(sql, engine_name, models)
    try:
        _, df = bigquery_engine.execute(sql)
        for col in ("stop_id",):
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df.to_dict(orient="records")
    except Exception:
        return []


@router.get("/models", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    """Return the list of allowed dbt models with column metadata."""
    raw_models = get_models()
    result: list[ModelInfo] = []
    for name, info in raw_models.items():
        cols = {}
        for col_name, col_info in (info.columns or {}).items():
            cols[col_name] = ModelColumnInfo(
                name=col_name,
                type=getattr(col_info, "type", None),
                description=getattr(col_info, "description", None),
            )
        result.append(
            ModelInfo(
                name=name,
                fq_name=info.fq_name,
                description=getattr(info, "description", None),
                columns=cols,
            )
        )
    return ModelsResponse(models=result)
