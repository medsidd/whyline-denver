"""Download endpoints — mart CSV exports and DuckDB warehouse."""

from __future__ import annotations

import io
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_guardrail_config, get_models
from api.models import MartDownloadRequest
from whyline.engines import bigquery_engine, duckdb_engine
from whyline.llm import adapt_sql_for_engine
from whyline.logs import log_query, query_cache
from whyline.sql_guardrails import SqlValidationError, sanitize_sql

router = APIRouter()

# Keep in sync with app/components/results_viewer.py::MART_OPTIONS
MART_OPTIONS: list[tuple[str, str]] = [
    ("mart_reliability_by_route_day", "Reliability by route & day"),
    ("mart_reliability_by_stop_hour", "Reliability by stop & hour"),
    ("mart_crash_proximity_by_stop", "Crash proximity by stop"),
    ("mart_access_score_by_stop", "Access score by stop"),
    ("mart_vulnerability_by_stop", "Vulnerability by stop"),
    ("mart_priority_hotspots", "Priority hotspots"),
    ("mart_weather_impacts", "Weather impacts"),
]
ALLOWED_MARTS = {name for name, _ in MART_OPTIONS}

_warehouse_env = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
WAREHOUSE_PATH = Path(_warehouse_env).expanduser()
if not WAREHOUSE_PATH.is_absolute():
    WAREHOUSE_PATH = (ROOT / WAREHOUSE_PATH).resolve()


def _build_filename(mart: str, engine: str, date_filter: tuple | None) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    suffix = ""
    if date_filter:
        col, start, end = date_filter
        suffix = f"_{col}_{start}_{end}"
    return f"{mart}_{engine}{suffix}_{ts}.csv"


@router.post("/downloads/mart")
def download_mart(req: MartDownloadRequest) -> StreamingResponse:
    """Build a guarded SELECT * FROM {mart} and return as a streaming CSV."""
    if req.mart not in ALLOWED_MARTS:
        raise HTTPException(status_code=400, detail=f"Mart '{req.mart}' is not in the allow list")

    models = get_models()
    guardrail_config = get_guardrail_config(req.engine)
    engine_module = duckdb_engine if req.engine == "duckdb" else bigquery_engine

    # Build SQL — mirrors _prepare_mart_download in results_viewer.py
    sql = f"SELECT * FROM {req.mart}"
    conditions: list[str] = []
    date_filter: tuple | None = None
    if req.date_column and req.date_start and req.date_end:
        if req.date_start > req.date_end:
            raise HTTPException(status_code=400, detail="date_start must be on or before date_end")
        conditions.append(
            f"{req.date_column} BETWEEN DATE '{req.date_start}' AND DATE '{req.date_end}'"
        )
        date_filter = (req.date_column, req.date_start, req.date_end)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += f" LIMIT {int(req.limit_rows)}"

    try:
        sanitized = sanitize_sql(sql, guardrail_config)
        adapted = adapt_sql_for_engine(sanitized, req.engine, models)
    except SqlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cached = query_cache.get(req.engine, sanitized)
    cache_hit = False
    latency_ms = 0.0
    if cached:
        stats, df = cached
        cache_hit = True
    else:
        try:
            start_time = time.monotonic()
            stats, df = engine_module.execute(adapted)
            latency_ms = (time.monotonic() - start_time) * 1000
            query_cache.set(req.engine, sanitized, (stats, df))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    log_query(
        engine=req.engine,
        rows=len(df),
        latency_ms=latency_ms,
        models=[req.mart],
        sql=sanitized,
        question=f"[download] {req.mart}",
        cache_hit=cache_hit,
        bq_est_bytes=stats.get("bq_est_bytes") if isinstance(stats, dict) else None,
    )

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    filename = _build_filename(req.mart, req.engine, date_filter)

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/downloads/warehouse")
def download_warehouse() -> StreamingResponse:
    """Return the local DuckDB warehouse file as a binary download."""
    if not WAREHOUSE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"DuckDB warehouse not found at {WAREHOUSE_PATH}. Run 'make sync-duckdb'.",
        )
    data = WAREHOUSE_PATH.read_bytes()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{WAREHOUSE_PATH.name}"'},
    )
