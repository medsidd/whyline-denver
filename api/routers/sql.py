"""SQL generation, validation, and prebuilt query endpoints."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_guardrail_config, get_models, get_schema_brief
from api.models import (
    GenerateSqlRequest,
    GenerateSqlResponse,
    ValidateSqlRequest,
    ValidateSqlResponse,
)
from whyline.engines import bigquery_engine
from whyline.llm import adapt_sql_for_engine, build_prompt, call_provider
from whyline.logs import prompt_cache
from whyline.sql_guardrails import SqlValidationError, sanitize_sql

# Prebuilt queries — identical to app/components/prebuilt_questions.py::PREBUILT
PREBUILT: list[tuple[str, str]] = [
    (
        "Worst 10 routes (last 30 days)",
        "SELECT route_id, AVG(pct_on_time) AS avg_pct_on_time\n"
        "FROM mart_reliability_by_route_day\n"
        "WHERE service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)\n"
        "GROUP BY route_id\n"
        "ORDER BY avg_pct_on_time ASC\n"
        "LIMIT 10",
    ),
    (
        "Stops with highest crash exposure",
        "SELECT stop_id, crash_250m_cnt\n"
        "FROM mart_crash_proximity_by_stop\n"
        "ORDER BY crash_250m_cnt DESC\n"
        "LIMIT 20",
    ),
    (
        "Where snow hurts reliability most",
        "SELECT route_id, delta_pct_on_time\n"
        "FROM mart_weather_impacts\n"
        "WHERE precip_bin IN ('mod', 'heavy')\n"
        "ORDER BY delta_pct_on_time ASC\n"
        "LIMIT 10",
    ),
    (
        "Equity gaps (high vulnerability, low reliability)",
        "SELECT p.stop_id, v.vuln_score_0_100, r.reliability_score_0_100, p.priority_score\n"
        "FROM mart_priority_hotspots p\n"
        "JOIN mart_vulnerability_by_stop v USING(stop_id)\n"
        "JOIN (\n"
        "  SELECT stop_id, 100 * (1 - AVG(pct_on_time)) AS reliability_score_0_100\n"
        "  FROM mart_reliability_by_stop_hour\n"
        "  WHERE service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 35 DAY)\n"
        "  GROUP BY stop_id\n"
        ") r USING(stop_id)\n"
        "ORDER BY p.priority_score DESC\n"
        "LIMIT 20",
    ),
]


def _add_filter_clauses(sql: str, filters) -> str:
    """Inject WHERE clauses — mirrors app/utils/sql_filters.py::add_filter_clauses."""
    import re

    def inject(s: str, column: str, condition: str) -> str:
        pattern = re.compile(
            r"(WHERE\s.*?)(\bGROUP BY\b|\bORDER BY\b|\bHAVING\b|\bLIMIT\b|$)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(s)
        if m:
            where_clause = m.group(1)
            if condition in where_clause:
                return s
            updated = where_clause.rstrip() + f"\n    AND {condition}\n"
            start, end = m.span(1)
            return s[:start] + updated + s[end:]
        ins = re.compile(r"\b(GROUP BY|ORDER BY|HAVING|LIMIT)\b", re.IGNORECASE)
        im = ins.search(s)
        pos = im.start() if im else len(s)
        return f"{s[:pos]}\nWHERE {condition}\n{s[pos:]}"

    lower = sql.lower()
    start = filters.start_date
    end = filters.end_date
    if start and end and "service_date_mst" in lower:
        sql = inject(
            sql, "service_date_mst", f"service_date_mst BETWEEN DATE '{start}' AND DATE '{end}'"
        )

    routes = filters.routes or []
    if routes and "route_id" in lower:
        formatted = ", ".join(f"'{r}'" for r in routes)
        sql = inject(sql, "route_id", f"route_id IN ({formatted})")

    stop_id = (filters.stop_id or "").strip()
    if stop_id and "stop_id" in lower:
        safe = stop_id.replace("'", "''").upper()
        sql = inject(sql, "stop_id", f"stop_id = '{safe}'")

    weather = filters.weather or []
    if weather and "precip_bin" in lower:
        formatted = ", ".join(f"'{b}'" for b in weather)
        sql = inject(sql, "precip_bin", f"precip_bin IN ({formatted})")

    return sql


router = APIRouter()


@router.post("/sql/generate", response_model=GenerateSqlResponse)
def generate_sql(req: GenerateSqlRequest) -> GenerateSqlResponse:
    """
    Convert a natural language question to SQL using the LLM provider.
    Checks prompt_cache before calling the LLM.
    """
    models = get_models()
    schema_brief = get_schema_brief()
    guardrail_config = get_guardrail_config(req.engine)
    provider = os.getenv("LLM_PROVIDER", "stub").lower()

    # Convert FilterState to dict for prompt_cache and add_filter_clauses
    filters_dict = req.filters.model_dump()

    cache_entry = prompt_cache.get(provider, req.engine, req.question, filters_dict)
    if cache_entry:
        cached_sql = cache_entry.get("sql", "")
        cached_explanation = cache_entry.get("explanation", "")
        try:
            sanitized = sanitize_sql(cached_sql, guardrail_config)
            sanitized = adapt_sql_for_engine(sanitized, req.engine, models)
        except SqlValidationError as exc:
            return GenerateSqlResponse(sql="", explanation="", error=str(exc))
        return GenerateSqlResponse(
            sql=sanitized,
            explanation=cached_explanation,
            cache_hit=True,
        )

    # No cache hit — call the LLM
    prompt = build_prompt(req.question, filters_dict, schema_brief)
    try:
        llm_output = call_provider(prompt)
    except NotImplementedError as exc:
        return GenerateSqlResponse(sql="", explanation="", error=str(exc))
    except Exception as exc:
        return GenerateSqlResponse(sql="", explanation="", error=f"LLM provider error: {exc}")

    candidate_sql = llm_output.get("sql", "")
    candidate_sql = _add_filter_clauses(candidate_sql, req.filters)
    try:
        sanitized = sanitize_sql(candidate_sql, guardrail_config)
        sanitized = adapt_sql_for_engine(sanitized, req.engine, models)
    except SqlValidationError as exc:
        return GenerateSqlResponse(sql="", explanation="", error=str(exc))

    explanation = llm_output.get("explanation", "")
    prompt_cache.set(
        provider,
        req.engine,
        req.question,
        filters_dict,
        {"sql": sanitized, "explanation": explanation},
    )

    return GenerateSqlResponse(sql=sanitized, explanation=explanation)


@router.post("/sql/validate", response_model=ValidateSqlResponse)
def validate_sql(req: ValidateSqlRequest) -> ValidateSqlResponse:
    """
    Validate and sanitize SQL. Optionally runs a BigQuery dry-run estimate.
    """
    models = get_models()
    guardrail_config = get_guardrail_config(req.engine)

    try:
        sanitized = sanitize_sql(req.sql, guardrail_config)
        sanitized = adapt_sql_for_engine(sanitized, req.engine, models)
    except SqlValidationError as exc:
        return ValidateSqlResponse(valid=False, error=str(exc))

    bq_est_bytes: int | None = None
    if req.engine == "bigquery":
        try:
            estimate_stats = bigquery_engine.estimate(sanitized)
            bq_est_bytes = estimate_stats.get("bq_est_bytes")
        except Exception:
            pass  # estimate failure is non-fatal

    return ValidateSqlResponse(valid=True, sanitized_sql=sanitized, bq_est_bytes=bq_est_bytes)


@router.post("/sql/prebuilt/{index}", response_model=GenerateSqlResponse)
def prebuilt_sql(index: int) -> GenerateSqlResponse:
    """
    Return a pre-validated prebuilt query by index (0–3).
    Accepts engine via query parameter.
    """
    if index < 0 or index >= len(PREBUILT):
        raise HTTPException(
            status_code=404, detail=f"Prebuilt index {index} not found (0–{len(PREBUILT) - 1})"
        )
    label, sql = PREBUILT[index]
    return GenerateSqlResponse(
        sql=sql,
        explanation=f"Prebuilt query: {label}",
    )


@router.post("/sql/prebuilt/{index}/for/{engine_name}", response_model=GenerateSqlResponse)
def prebuilt_sql_for_engine(index: int, engine_name: str) -> GenerateSqlResponse:
    """
    Return a prebuilt query validated and adapted for the given engine.
    """
    if engine_name not in ("duckdb", "bigquery"):
        raise HTTPException(status_code=400, detail="engine must be 'duckdb' or 'bigquery'")
    if index < 0 or index >= len(PREBUILT):
        raise HTTPException(status_code=404, detail=f"Prebuilt index {index} not found")

    label, sql = PREBUILT[index]
    models = get_models()
    guardrail_config = get_guardrail_config(engine_name)

    try:
        sanitized = sanitize_sql(sql, guardrail_config)
        sanitized = adapt_sql_for_engine(sanitized, engine_name, models)
    except SqlValidationError as exc:
        return GenerateSqlResponse(sql="", explanation="", error=str(exc))

    return GenerateSqlResponse(
        sql=sanitized,
        explanation=f"Prebuilt query: {label}",
    )
