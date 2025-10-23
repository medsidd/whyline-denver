from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from whylinedenver.config import settings
from whylinedenver.semantics.dbt_artifacts import ModelInfo
from whylinedenver.sql_guardrails import GuardrailConfig, sanitize_sql


def build_schema_brief(models: Mapping[str, ModelInfo], *, max_columns: int = 5) -> str:
    lines: list[str] = []
    for model in sorted(models.values(), key=lambda m: m.name):
        description = model.description or "No description available."
        lines.append(f"- {model.name}: {description}")
        columns = list(model.columns.items())[:max_columns]
        for column_name, info in columns:
            col_desc = info.description or "No column description available."
            col_type = info.type or "UNKNOWN"
            lines.append(f"    • {column_name} ({col_type}): {col_desc}")
    return "\n".join(lines)


def build_prompt(question: str, filters: Mapping[str, Any] | None, schema_brief: str) -> str:
    filters = filters or {}
    filters_serialized = "\n".join(f"- {key}: {value}" for key, value in filters.items()) or "None"
    instructions = (
        "You are a SQL expert for the WhyLine Denver transit analytics platform.\n"
        "Respond with a single SELECT statement that adheres to the following:\n"
        "- Only query the provided mart tables.\n"
        "- Apply relevant filters when possible.\n"
        "- Keep results under 5,000 rows.\n"
        "- Return helpful column aliases that match the question.\n"
        "- Provide a short natural-language explanation of the query intent."
    )
    return (
        f"{instructions}\n\n"
        f"Question:\n{question}\n\n"
        f"User filters:\n{filters_serialized}\n\n"
        f"Schema brief:\n{schema_brief}\n\n"
        "Return JSON with keys 'sql' and 'explanation'."
    )


@dataclass(slots=True)
class LlmResponse:
    sql: str
    explanation: str


def call_provider(prompt: str) -> Dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "stub").lower()
    if provider != "stub":
        raise NotImplementedError(f"LLM provider '{provider}' is not implemented yet.")
    return _stubbed_response(prompt)


def _stubbed_response(prompt: str) -> Dict[str, str]:
    lower_prompt = prompt.lower()
    if "worst" in lower_prompt and "route" in lower_prompt:
        return {
            "sql": (
                "SELECT route_id,\n"
                "       AVG(1 - pct_on_time) AS avg_delay_ratio,\n"
                "       AVG(mean_delay_sec) AS avg_delay_seconds\n"
                "FROM mart_reliability_by_route_day\n"
                "WHERE service_date_mst >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)\n"
                "GROUP BY route_id\n"
                "ORDER BY avg_delay_ratio DESC\n"
                "LIMIT 10"
            ),
            "explanation": "Ranks routes by average delay ratio over the past 30 days.",
        }
    return {
        "sql": ("SELECT *\n" "FROM mart_access_score_by_stop\n" "LIMIT 100"),
        "explanation": "Default stub query returning access scores.",
    }


def ask(
    question: str,
    *,
    filters: Mapping[str, Any] | None,
    models: Mapping[str, ModelInfo],
    allowlist: set[str],
    engine: str,
) -> LlmResponse:
    schema_brief = build_schema_brief(models)
    prompt = build_prompt(question, filters, schema_brief)
    raw_response = call_provider(prompt)
    sql = raw_response.get("sql", "")
    explanation = raw_response.get("explanation", "")
    sql = adapt_sql_for_engine(sql, engine, models)
    config = GuardrailConfig(allowed_models=allowlist, engine=engine)
    sanitized_sql = sanitize_sql(sql, config)
    return LlmResponse(sql=sanitized_sql, explanation=explanation)


DATE_SUB_PATTERN = re.compile(
    r"DATE_SUB\(\s*(.+?)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)", re.IGNORECASE
)
TABLE_PATTERN = re.compile(
    r"\b(?P<clause>FROM|JOIN)\s+(?P<table>[`\w.]+)(?P<alias>\s+AS\s+\w+|\s+\w+)?",
    re.IGNORECASE,
)


def adapt_sql_for_engine(
    sql: str, engine: str, models: Mapping[str, ModelInfo] | None = None
) -> str:
    transformed = sql
    if engine == "duckdb":
        transformed = DATE_SUB_PATTERN.sub(_duckdb_date_sub_replacer, transformed)
    if engine == "bigquery" and models:
        transformed = _qualify_bigquery_tables(transformed, models)
    return transformed


def _duckdb_date_sub_replacer(match: re.Match[str]) -> str:
    expr = match.group(1).strip()
    days = match.group(2)
    return f"{expr} - INTERVAL '{days}' DAY"


def _qualify_bigquery_tables(sql: str, models: Mapping[str, ModelInfo]) -> str:
    def replacer(match: re.Match[str]) -> str:
        table_token = match.group("table")
        alias = match.group("alias") or ""
        raw_table = table_token.strip("`")
        if "." in raw_table:
            return match.group(0)
        model = models.get(raw_table)
        table_name = model.name if model else raw_table
        qualified = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{table_name}`"
        return f"{match.group('clause')} {qualified}{alias}"

    return TABLE_PATTERN.sub(replacer, sql)


__all__ = [
    "adapt_sql_for_engine",
    "ask",
    "build_prompt",
    "build_schema_brief",
    "call_provider",
    "LlmResponse",
]
