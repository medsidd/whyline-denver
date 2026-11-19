"""SQL generation, validation, and prebuilt query endpoints."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from google.api_core.exceptions import GoogleAPICallError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.deps import get_guardrail_config, get_models, get_schema_brief
from api.models import (
    FilterState,
    GenerateSqlRequest,
    GenerateSqlResponse,
    ValidateSqlRequest,
    ValidateSqlResponse,
)
from whyline.engines import bigquery_engine
from whyline.llm import build_prompt, call_provider, qualify_tables
from whyline.logs import prompt_cache
from whyline.prebuilt import (
    PREBUILT,
    build_prebuilt_sql,
    clean_filters,
    date_predicate,
    is_live,
    route_predicate,
    stop_predicate,
    weather_predicate,
)
from whyline.sql_guardrails import SqlValidationError, sanitize_sql


def _add_filter_clauses(sql: str, filters) -> str:
    """Inject filter-rail WHERE clauses into generated SQL; values are validated first."""
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
    f = clean_filters(filters.model_dump())
    if f.start_date and "service_date_mst" in lower:
        sql = inject(sql, "service_date_mst", date_predicate(f))
    if f.routes and "route_id" in lower:
        sql = inject(sql, "route_id", route_predicate(f))
    if f.stop_id and "stop_id" in lower:
        sql = inject(sql, "stop_id", stop_predicate(f))
    if f.weather and "precip_bin" in lower:
        sql = inject(sql, "precip_bin", weather_predicate(f))

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
    guardrail_config = get_guardrail_config()
    provider = os.getenv("LLM_PROVIDER", "stub").lower()

    # Convert FilterState to dict for prompt_cache and add_filter_clauses
    filters_dict = req.filters.model_dump()

    cache_entry = prompt_cache.get(provider, req.question, filters_dict)
    if cache_entry:
        cached_sql = cache_entry.get("sql", "")
        cached_explanation = cache_entry.get("explanation", "")
        try:
            sanitized = sanitize_sql(cached_sql, guardrail_config)
            sanitized = qualify_tables(sanitized, models)
        except SqlValidationError as exc:
            return GenerateSqlResponse(sql="", explanation="", error=str(exc))
        return GenerateSqlResponse(
            sql=sanitized,
            explanation=cached_explanation,
            cache_hit=True,
            is_live=is_live(sanitized),
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
        sanitized = qualify_tables(sanitized, models)
    except SqlValidationError as exc:
        return GenerateSqlResponse(sql="", explanation="", error=str(exc))

    explanation = llm_output.get("explanation", "")
    prompt_cache.set(
        provider,
        req.question,
        filters_dict,
        {"sql": sanitized, "explanation": explanation},
    )

    return GenerateSqlResponse(sql=sanitized, explanation=explanation, is_live=is_live(sanitized))


@router.post("/sql/validate", response_model=ValidateSqlResponse)
def validate_sql(req: ValidateSqlRequest) -> ValidateSqlResponse:
    """
    Validate and sanitize SQL. Optionally runs a BigQuery dry-run estimate.
    """
    models = get_models()
    guardrail_config = get_guardrail_config()

    try:
        sanitized = sanitize_sql(req.sql, guardrail_config)
        sanitized = qualify_tables(sanitized, models)
    except SqlValidationError as exc:
        return ValidateSqlResponse(valid=False, error=str(exc))

    bq_est_bytes: int | None = None
    try:
        estimate_stats = bigquery_engine.estimate(
            sanitized, allowed_tables=guardrail_config.allowed_models
        )
        bq_est_bytes = estimate_stats.get("bq_est_bytes")
    except SqlValidationError as exc:
        # BigQuery's own parse found a table or statement the text checks missed
        return ValidateSqlResponse(valid=False, error=str(exc))
    except GoogleAPICallError as exc:
        # BigQuery refused the query (syntax, unknown column, missing table); running it
        # would fail the same way
        reason = (exc.errors or [{}])[0].get("message") or exc.message or str(exc)
        return ValidateSqlResponse(valid=False, error=reason)
    except Exception:
        pass  # no credentials or network: the estimate is optional

    return ValidateSqlResponse(
        valid=True, sanitized_sql=sanitized, bq_est_bytes=bq_est_bytes, is_live=is_live(sanitized)
    )


@router.post("/sql/prebuilt/{index}", response_model=GenerateSqlResponse)
def prebuilt_sql(index: int, filters: FilterState | None = None) -> GenerateSqlResponse:
    """A ready-made question with the filters it supports, checked and ready to run."""
    if index < 0 or index >= len(PREBUILT):
        raise HTTPException(
            status_code=404, detail=f"Prebuilt index {index} not found (0–{len(PREBUILT) - 1})"
        )
    built = build_prebuilt_sql(index, filters.model_dump() if filters else None)
    try:
        sanitized = sanitize_sql(built.sql, get_guardrail_config())
        sanitized = qualify_tables(sanitized, get_models())
    except SqlValidationError as exc:
        return GenerateSqlResponse(sql="", explanation="", error=str(exc))
    return GenerateSqlResponse(
        sql=sanitized,
        explanation=PREBUILT[index].explanation,
        applied_filters=built.applied,
        skipped_filters=built.skipped,
        is_live=is_live(built.sql),
    )


# shortcut: alias for the dashboard before it switched to the route above; delete once the
# frontend no longer calls it.
@router.post(
    "/sql/prebuilt/{index}/for/{engine_name}",
    response_model=GenerateSqlResponse,
    include_in_schema=False,
)
def prebuilt_sql_alias(
    index: int, engine_name: str, filters: FilterState | None = None
) -> GenerateSqlResponse:
    if engine_name != "bigquery":
        raise HTTPException(status_code=404, detail="Not Found")
    return prebuilt_sql(index, filters)
