"""Filter data endpoints — routes, weather bins, date range, stops, models."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_models
from api.models import (
    FilterOptionsResponse,
    ModelColumnInfo,
    ModelInfo,
    ModelsResponse,
    RouteShape,
)
from whyline.config import settings
from whyline.engines import bigquery_engine, duckdb_engine
from whyline.llm import adapt_sql_for_engine
from whyline.logs import QueryCache
from whyline.prebuilt import ROUTE_PATTERN

# Routes, weather bins and the date range change at most nightly; three BigQuery queries per
# page load took about 6 s.
_filters_cache = QueryCache(ttl_seconds=600)
# Route shapes change with the GTFS feed (nightly at most); the whole table is about 370 KB.
_shapes_cache = QueryCache(ttl_seconds=6 * 3600)
# A failed read (before the table's first build) is remembered briefly, so maps don't query
# BigQuery on every render; one request at a time fills the cache.
_shapes_failures = QueryCache(ttl_seconds=300)
_shapes_lock = threading.Lock()
MAX_SHAPE_ROUTES = 10


def _line_parts(geometry: dict) -> list[list[list[float]]]:
    """[lon, lat] paths of a LineString or MultiLineString with at least two points; other
    geometry types (a Point, if simplifying collapsed a tiny shape) give none."""
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    parts = [coords] if kind == "LineString" else coords if kind == "MultiLineString" else []
    return [
        [[float(c[0]), float(c[1])] for c in part]
        for part in parts
        if len(part) >= 2 and all(isinstance(c, list) and len(c) >= 2 for c in part)
    ]


router = APIRouter()


def _engine_module(engine_name: str):
    return duckdb_engine if engine_name == "duckdb" else bigquery_engine


def _qualify_table(engine_name: str, table: str) -> str:
    if engine_name == "bigquery":
        return f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{table}`"
    return table


@router.get("/filters/{engine_name}", response_model=FilterOptionsResponse)
def get_filters(engine_name: str) -> FilterOptionsResponse:
    """Return routes, weather bins, and date range for the selected engine."""
    if engine_name not in ("duckdb", "bigquery"):
        raise HTTPException(status_code=400, detail="engine must be 'duckdb' or 'bigquery'")

    cached = _filters_cache.get(engine_name, "filters")
    if cached:
        return cached
    response = _load_filters(engine_name)
    if response.error is None:
        _filters_cache.set(engine_name, "filters", response)
    return response


def _load_filters(engine_name: str) -> FilterOptionsResponse:
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
    weather_bins: list[str] = ["none", "light", "mod", "heavy"]
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
    table = _qualify_table(engine_name, "mart_gtfs_stops")
    sql = f"SELECT stop_id, stop_name, lat AS stop_lat, lon AS stop_lon FROM {table}"
    sql = adapt_sql_for_engine(sql, engine_name, models)
    try:
        _, df = bigquery_engine.execute(sql)
        for col in ("stop_id",):
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df.to_dict(orient="records")
    except Exception:
        return []


def _all_route_shapes() -> dict[str, list[dict]]:
    """Every route's shapes from mart_route_shapes, by route_id; cached unless the query failed."""
    with _shapes_lock:
        cached = _shapes_cache.get("bigquery", "route_shapes")
        if cached is not None:
            return cached
        if _shapes_failures.get("bigquery", "route_shapes"):
            raise RuntimeError("route shapes unavailable (recent failure)")
        table = _qualify_table("bigquery", "mart_route_shapes")
        try:
            _, df = bigquery_engine.execute(f"SELECT route_id, direction_id, geojson FROM {table}")
        except Exception:
            _shapes_failures.set("bigquery", "route_shapes", True)
            raise
        shapes: dict[str, list[dict]] = {}
        for row in df.itertuples(index=False):
            # Simplifying can split a shape (a third of RTD's): one path per part
            for part in _line_parts(json.loads(row.geojson)):
                shapes.setdefault(str(row.route_id), []).append(
                    {"direction_id": int(row.direction_id), "path": part}
                )
        _shapes_cache.set("bigquery", "route_shapes", shapes)
        return shapes


@router.get("/routes/shapes", response_model=list[RouteShape])
def get_route_shapes(ids: str = "") -> list[RouteShape]:
    """Paths for up to MAX_SHAPE_ROUTES route IDs (comma-separated), in the order given.

    Unknown or invalid IDs are skipped. If the shapes table can't be read (before its first
    nightly build), the answer is empty: maps then show stops only.
    """
    wanted = [
        r for r in dict.fromkeys(i.strip() for i in ids.split(",")) if ROUTE_PATTERN.fullmatch(r)
    ]
    try:
        shapes = _all_route_shapes()
    except Exception:  # noqa: BLE001 - a missing table must not break the map
        return []
    return [
        RouteShape(route_id=r, direction_id=s["direction_id"], path=s["path"])
        for r in wanted[:MAX_SHAPE_ROUTES]
        for s in shapes.get(r, [])
    ]


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
