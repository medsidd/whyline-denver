"""Query execution endpoint — POST /api/query/run."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_allowlist, get_guardrail_config, get_models
from api.models import RunQueryRequest, RunQueryResponse
from whyline.engines import bigquery_engine, duckdb_engine
from whyline.llm import adapt_sql_for_engine
from whyline.logs import log_query, query_cache
from whyline.sql_guardrails import SqlValidationError, sanitize_sql

router = APIRouter()

_MAX_DISPLAY_ROWS = 10_000


@router.post("/query/run", response_model=RunQueryResponse)
def run_query(req: RunQueryRequest) -> RunQueryResponse:
    """
    Validate and execute SQL, returning up to 10,000 rows for display.
    Always re-sanitizes server-side regardless of what the client sends.
    Checks query_cache before executing; logs every query.
    """
    models = get_models()
    allowlist = get_allowlist()
    guardrail_config = get_guardrail_config(req.engine)
    engine_module = duckdb_engine if req.engine == "duckdb" else bigquery_engine

    # Server-side re-validation (never trust client SQL)
    try:
        sanitized = sanitize_sql(req.sql, guardrail_config)
        sanitized = adapt_sql_for_engine(sanitized, req.engine, models)
    except SqlValidationError as exc:
        return RunQueryResponse(rows=0, columns=[], data=[], total_rows=0, stats={}, error=str(exc))

    # Check cache
    cached = query_cache.get(req.engine, sanitized)
    cache_hit = False
    latency_ms = 0.0
    stats: dict = {}

    try:
        if cached:
            raw_stats, df = cached
            stats = raw_stats if isinstance(raw_stats, dict) else {}
            cache_hit = True
        else:
            start = time.monotonic()
            raw_stats, df = engine_module.execute(sanitized)
            latency_ms = (time.monotonic() - start) * 1000
            stats = raw_stats if isinstance(raw_stats, dict) else {}
            query_cache.set(req.engine, sanitized, (raw_stats, df))

        log_query(
            engine=req.engine,
            rows=len(df),
            latency_ms=latency_ms,
            models=list(allowlist),
            sql=sanitized,
            question=req.question,
            cache_hit=cache_hit,
            bq_est_bytes=stats.get("bq_est_bytes"),
        )

        total_rows = len(df)
        display_df = df.head(_MAX_DISPLAY_ROWS)

        # Ensure JSON-serializable types
        for col in display_df.columns:
            if display_df[col].dtype.name.startswith("datetime"):
                display_df = display_df.copy()
                display_df[col] = display_df[col].astype(str)

        return RunQueryResponse(
            rows=min(total_rows, _MAX_DISPLAY_ROWS),
            columns=list(df.columns),
            data=display_df.to_dict(orient="records"),
            total_rows=total_rows,
            stats=stats,
        )

    except Exception as exc:
        return RunQueryResponse(rows=0, columns=[], data=[], total_rows=0, stats={}, error=str(exc))
