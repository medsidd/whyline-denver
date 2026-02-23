from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, Mapping

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency for stub mode
    genai = None

from whyline.config import settings
from whyline.semantics.dbt_artifacts import ModelInfo
from whyline.sql_guardrails import CTE_PATTERN


def build_schema_brief(models: Mapping[str, ModelInfo], *, max_columns: int = 7) -> str:
    """Condense model metadata for prompt conditioning."""

    lines: list[str] = []
    for model in sorted(models.values(), key=lambda m: m.name):
        description = (model.description or "")[:80]
        column_names = ", ".join(list(model.columns.keys())[:max_columns])
        line = f"{model.name}: {description} | cols: {column_names}"
        lines.append(line.strip())
    return "\n".join(lines)


def build_prompt(question: str, filters: Mapping[str, Any] | None, schema_brief: str) -> str:
    filters = filters or {}
    filters_serialized = json.dumps(filters, indent=2, sort_keys=True) if filters else "{}"
    return (
        "You are a SQL generation assistant for the WhyLine Denver transit analytics platform.\n"
        "You may query ONLY these models:\n"
        f"{schema_brief}\n\n"
        "Return a JSON object with keys 'sql' and 'explanation'.\n"
        "- 'sql' must contain a single DuckDB/BigQuery compatible SELECT statement.\n"
        "- Do not include semicolons or additional statements.\n"
        "- 'explanation' must be 2-3 succinct sentences for non-technical transit stakeholders,\n"
        "  describing what insights the query surfaces and why it matters.\n"
        "- All FROM/JOIN sources must come from the allow-listed models; derive comparisons using CTEs or subqueries built on those tables.\n"
        "- Keep results under 5,000 rows and honor recency cues by filtering service_date_mst within 30-90 days when appropriate.\n"
        "- Treat the user filters below as scalar values only—never reference them as tables or views.\n"
        "- Do not invent placeholder tables (e.g., filters, zero, baseline); name any CTEs you create based on the metrics being calculated.\n"
        "- When analyzing crash trends described as 'this month', 'recent', or 'last few days', default to window_days = 30 on mart_crash_proximity_by_stop and anchor comparisons on the latest as_of_date values.\n"
        "- Prefer analytic window functions such as LAG() and ROW_NUMBER() to calculate change over time instead of fabricating previous_* tables.\n"
        "- Include severity metrics (fatal and severe crash counts) alongside total crashes when the question focuses on risk or hotspots.\n\n"
        f"Question: {question}\n"
        "User filters (values only):\n"
        f"{filters_serialized}\n"
    )


def call_provider(prompt: str) -> Dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "stub").lower()

    if provider == "gemini":
        return _gemini_response(prompt)

    if provider in {"stub", "default"}:
        return _stubbed_response(prompt)

    raise NotImplementedError(f"LLM provider '{provider}' is not implemented yet.")


@lru_cache(maxsize=1)
def _init_gemini_model():
    if genai is None:
        raise RuntimeError(
            "google-generativeai is not installed. Install requirements.txt to use Gemini."
        )

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    return genai.GenerativeModel(model_name)


def _gemini_response(prompt: str) -> Dict[str, str]:
    model = _init_gemini_model()
    response = model.generate_content(prompt)

    text = getattr(response, "text", None)
    if not text and hasattr(response, "candidates"):
        parts = []
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []):
                part_text = getattr(part, "text", None)
                if part_text:
                    parts.append(part_text)
        text = "\n".join(parts)

    if not text:
        raise RuntimeError("Gemini returned an empty response.")

    payload = _strip_code_fence(text)
    data = _parse_response_payload(payload)
    return data


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences and language hints from model output."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        if "\n" in cleaned:
            _language, cleaned = cleaned.split("\n", 1)
        else:
            cleaned = ""
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip().strip("`")


def _parse_response_payload(payload: str) -> Dict[str, str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
        raise RuntimeError(f"Gemini response was not valid JSON: {exc}") from exc

    sql = _strip_code_fence(data.get("sql") or "").strip()
    explanation = (data.get("explanation") or "").strip()
    if not sql:
        raise RuntimeError("Gemini response missing 'sql'.")
    if not explanation:
        explanation = "Generated by Gemini."
    return {"sql": sql, "explanation": explanation}


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
            "explanation": (
                "Finds the ten routes with the most severe delays over the past month, "
                "highlighting where riders feel the biggest pain today."
            ),
        }
    return {
        "sql": ("SELECT *\n" "FROM mart_access_score_by_stop\n" "LIMIT 100"),
        "explanation": "Default stub query returning access scores.",
    }


DATE_SUB_PATTERN = re.compile(
    r"DATE_SUB\(\s*(.+?)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)", re.IGNORECASE
)
TABLE_PATTERN = re.compile(
    r"\b(?P<clause>FROM|JOIN)\s+"
    r"(?P<table>(?:`[^`]+`|[\w-]+)(?:\.(?:`[^`]+`|[\w-]+)){0,2})"
    r"(?P<alias>\s+AS\s+\w+|\s+\w+)?",
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
    cte_names = {name.strip("`").lower() for name in CTE_PATTERN.findall(sql)}

    def replacer(match: re.Match[str]) -> str:
        table_token = match.group("table")
        alias = match.group("alias") or ""
        raw_table = table_token.strip("`")
        if raw_table.lower() in cte_names:
            return match.group(0)
        if "." in raw_table:
            return match.group(0)
        model = models.get(raw_table)
        table_name = model.name if model else raw_table
        qualified = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{table_name}`"
        return f"{match.group('clause')} {qualified}{alias}"

    return TABLE_PATTERN.sub(replacer, sql)


__all__ = [
    "adapt_sql_for_engine",
    "build_prompt",
    "build_schema_brief",
    "call_provider",
]
