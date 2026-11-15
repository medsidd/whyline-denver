"""Download endpoints — mart CSV exports and DuckDB warehouse."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterator

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_guardrail_config, get_models
from api.models import MartDownloadRequest
from whyline.engines import bigquery_engine, duckdb_engine
from whyline.llm import adapt_sql_for_engine
from whyline.logs import log_query
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
    ("mart_service_frequency_by_stop", "Scheduled departures by stop & hour"),
    ("mart_frequent_network_by_route", "Route frequency & span"),
    ("mart_service_intensity_by_tract", "Scheduled service by census tract"),
    ("mart_prediction_accuracy_by_route_day", "Arrival-prediction accuracy by route & day"),
    ("mart_crowding_by_route_hour", "Crowding by route & hour"),
    ("mart_crowding_by_stop", "Crowding by stop & hour"),
    ("mart_service_delivered_by_route_day", "Missed trips by route & day"),
    ("mart_wait_by_stop_period", "Wait time by stop & time of day"),
    ("mart_wait_by_route_day", "Wait time by route & day"),
    ("mart_segment_speed_by_hour", "Speed between stops by hour"),
    ("mart_trip_runtime_by_route_day", "Trip run time by route & day"),
]
ALLOWED_MARTS = {name for name, _ in MART_OPTIONS}
# Marts that may be date-filtered, always on service_date_mst; the others have no service date.
DATED_MARTS = frozenset(
    (
        "mart_reliability_by_route_day",
        "mart_reliability_by_stop_hour",
        "mart_prediction_accuracy_by_route_day",
        "mart_crowding_by_route_hour",
        "mart_service_delivered_by_route_day",
        "mart_wait_by_route_day",
        "mart_trip_runtime_by_route_day",
    )
)

_warehouse_env = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
WAREHOUSE_PATH = Path(_warehouse_env).expanduser()
if not WAREHOUSE_PATH.is_absolute():
    WAREHOUSE_PATH = (ROOT / WAREHOUSE_PATH).resolve()

# A download holds its whole result in memory (up to MartDownloadRequest's row limit), so
# only this many may build at once per instance; the rest get a 429 and retry.
_download_slots = threading.BoundedSemaphore(2)
_CSV_CHUNK_ROWS = 50_000


def _csv_chunks(df: pd.DataFrame) -> Iterator[bytes]:
    """The CSV in pieces, so the text is never held whole next to the DataFrame."""
    if df.empty:
        yield df.to_csv(index=False).encode("utf-8")
    for start in range(0, len(df), _CSV_CHUNK_ROWS):
        chunk = df.iloc[start : start + _CSV_CHUNK_ROWS]
        yield chunk.to_csv(index=False, header=start == 0).encode("utf-8")


def _build_filename(mart: str, engine: str, date_filter: tuple | None) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = ""
    if date_filter:
        col, start, end = date_filter
        suffix = f"_{col}_{start}_{end}"
    return f"{mart}_{engine}{suffix}_{ts}.csv"


def _build_download_sql(req: MartDownloadRequest) -> tuple[str, tuple | None]:
    """SELECT * for the mart, within validated dates and newest first when it has a service date."""
    sql = f"SELECT * FROM {req.mart}"
    date_filter: tuple | None = None
    if req.date_column and req.date_start and req.date_end:
        if req.mart not in DATED_MARTS or req.date_column != "service_date_mst":
            raise HTTPException(
                status_code=400,
                detail=f"'{req.date_column}' is not a date column of {req.mart}",
            )
        try:
            start, end = date.fromisoformat(req.date_start), date.fromisoformat(req.date_end)
        except ValueError:
            raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
        if start > end:
            raise HTTPException(status_code=400, detail="date_start must be on or before date_end")
        sql += f" WHERE {req.date_column} BETWEEN DATE '{start}' AND DATE '{end}'"
        date_filter = (req.date_column, start, end)
    if req.mart in DATED_MARTS:
        # The BigQuery guardrail wants a WHERE wherever service_date_mst appears.
        if date_filter is None:
            sql += " WHERE service_date_mst IS NOT NULL"
        # Without an order the limit kept arbitrary rows; keep the newest.
        sql += " ORDER BY service_date_mst DESC"
    return f"{sql} LIMIT {int(req.limit_rows)}", date_filter


@router.post("/downloads/mart")
def download_mart(req: MartDownloadRequest) -> StreamingResponse:
    """Build a guarded SELECT * FROM {mart} and return as a streaming CSV."""
    if req.mart not in ALLOWED_MARTS:
        raise HTTPException(status_code=400, detail=f"Mart '{req.mart}' is not in the allow list")

    models = get_models()
    guardrail_config = get_guardrail_config(req.engine)
    engine_module = duckdb_engine if req.engine == "duckdb" else bigquery_engine

    sql, date_filter = _build_download_sql(req)

    try:
        sanitized = sanitize_sql(sql, guardrail_config)
        adapted = adapt_sql_for_engine(sanitized, req.engine, models)
    except SqlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not _download_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many downloads at once. Try again soon.")
    try:
        start_time = time.monotonic()
        # No max_rows: the SQL is built here with its own LIMIT, and an uncapped BigQuery read
        # can use the faster Storage API
        stats, df = engine_module.execute(adapted, allowed_tables=guardrail_config.allowed_models)
        latency_ms = (time.monotonic() - start_time) * 1000
    except SqlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        _download_slots.release()

    log_query(
        engine=req.engine,
        rows=len(df),
        latency_ms=latency_ms,
        models=[req.mart],
        sql=sanitized,
        question=f"[download] {req.mart}",
        cache_hit=False,
        bq_est_bytes=stats.get("bq_est_bytes") if isinstance(stats, dict) else None,
    )

    filename = _build_filename(req.mart, req.engine, date_filter)

    return StreamingResponse(
        _csv_chunks(df),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/downloads/warehouse")
def download_warehouse() -> FileResponse:
    """Return the local DuckDB warehouse file as a binary download, read from disk in pieces."""
    if not WAREHOUSE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"DuckDB warehouse not found at {WAREHOUSE_PATH}. Run 'make sync-duckdb'.",
        )
    return FileResponse(
        WAREHOUSE_PATH, media_type="application/octet-stream", filename=WAREHOUSE_PATH.name
    )
