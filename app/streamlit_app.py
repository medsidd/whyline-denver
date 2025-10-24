# ruff: noqa: E402,I001
from __future__ import annotations

import json
import os
import time
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from whylinedenver.config import settings  # noqa: E402
from whylinedenver.engines import bigquery_engine, duckdb_engine  # noqa: E402
from whylinedenver.llm import (
    adapt_sql_for_engine,
    build_prompt,
    build_schema_brief,
    call_provider,
)  # noqa: E402
from whylinedenver.logs import log_query, query_cache  # noqa: E402
from whylinedenver.semantics.dbt_artifacts import DbtArtifacts, ModelInfo  # noqa: E402
from whylinedenver.sql_guardrails import (  # noqa: E402
    GuardrailConfig,
    SqlValidationError,
    sanitize_sql,
)

st.set_page_config(page_title="WhyLine Denver", layout="wide")
st.title("WhyLine Denver — Natural-Language Explorer")


@st.cache_data
def load_allowed_models() -> dict[str, ModelInfo]:
    artifacts = DbtArtifacts()
    return artifacts.allowed_models()


@st.cache_data
def load_route_options() -> list[str]:
    try:
        _, df = duckdb_engine.execute(
            "SELECT DISTINCT route_id FROM mart_reliability_by_route_day "
            "WHERE route_id IS NOT NULL ORDER BY route_id LIMIT 200"
        )
        return df["route_id"].astype(str).tolist()
    except Exception:
        return []


@st.cache_data
def load_weather_bins() -> list[str]:
    try:
        _, df = duckdb_engine.execute(
            "SELECT DISTINCT precip_bin FROM mart_reliability_by_route_day "
            "WHERE precip_bin IS NOT NULL ORDER BY precip_bin"
        )
        return df["precip_bin"].astype(str).tolist()
    except Exception:
        return ["none", "rain", "snow"]


def human_readable_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024


@st.cache_data
def load_service_date_range() -> tuple[date | None, date | None]:
    try:
        _, df = duckdb_engine.execute(
            "SELECT MIN(service_date_mst) AS min_date, MAX(service_date_mst) AS max_date "
            "FROM mart_reliability_by_route_day"
        )
        if df.empty:
            return None, None
        min_timestamp = pd.to_datetime(df.loc[0, "min_date"])
        max_timestamp = pd.to_datetime(df.loc[0, "max_date"])
        if pd.isna(min_timestamp) or pd.isna(max_timestamp):
            return None, None
        min_date = min_timestamp.date()
        max_date = max_timestamp.date()
        return min_date, max_date
    except Exception:
        return None, None


def read_duckdb_freshness() -> str:
    path = Path("data/sync_state.json")
    if not path.exists():
        return "Unavailable"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ts = payload.get("refreshed_at_utc")
        return _format_timestamp(ts)
    except (json.JSONDecodeError, OSError):
        return "Unavailable"


def read_bigquery_freshness() -> str:
    path = Path("dbt/target/run_results.json")
    if not path.exists():
        return "Unavailable"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        timestamps: list[str] = []
        for result in payload.get("results", []):
            for timing in result.get("timing", []):
                completed_at = timing.get("completed_at")
                if completed_at:
                    timestamps.append(completed_at)
        if not timestamps:
            return "Unavailable"
        return _format_timestamp(max(timestamps))
    except (json.JSONDecodeError, OSError, ValueError):
        return "Unavailable"


def _format_timestamp(ts: str | None) -> str:
    if not ts:
        return "Unavailable"
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(ts)
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        try:
            parsed = datetime.utcfromtimestamp(float(ts))
            return parsed.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            return ts


def add_filter_clauses(sql: str, filters: Mapping[str, Any]) -> str:
    augmented_sql = sql
    lower_sql = sql.lower()

    start = filters.get("start_date")
    end = filters.get("end_date")
    if start and end and "service_date_mst" in lower_sql:
        augmented_sql = _inject_condition(
            augmented_sql,
            "service_date_mst",
            f"service_date_mst BETWEEN DATE '{start}' AND DATE '{end}'",
        )

    routes = filters.get("routes") or []
    if routes and "route_id" in lower_sql:
        formatted = ", ".join(f"'{route}'" for route in routes)
        augmented_sql = _inject_condition(augmented_sql, "route_id", f"route_id IN ({formatted})")

    stop_id = (filters.get("stop_id") or "").strip()
    if stop_id and "stop_id" in lower_sql:
        stop_safe = stop_id.replace("'", "''").upper()
        augmented_sql = _inject_condition(augmented_sql, "stop_id", f"stop_id = '{stop_safe}'")

    weather_bins = filters.get("weather") or []
    if weather_bins and "precip_bin" in lower_sql:
        formatted = ", ".join(f"'{bin}'" for bin in weather_bins)
        augmented_sql = _inject_condition(
            augmented_sql, "precip_bin", f"precip_bin IN ({formatted})"
        )

    return augmented_sql


def _inject_condition(sql: str, column: str, condition: str) -> str:
    pattern = re.compile(
        r"(WHERE\s.*?)(\bGROUP BY\b|\bORDER BY\b|\bHAVING\b|\bLIMIT\b|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    if match:
        where_clause = match.group(1)
        if condition in where_clause:
            return sql
        updated = where_clause.rstrip() + f"\n    AND {condition}\n"
        start, end = match.span(1)
        return sql[:start] + updated + sql[end:]

    insertion_pattern = re.compile(r"\b(GROUP BY|ORDER BY|HAVING|LIMIT)\b", re.IGNORECASE)
    insertion_match = insertion_pattern.search(sql)
    insert_pos = insertion_match.start() if insertion_match else len(sql)
    return f"{sql[:insert_pos]}\nWHERE {condition}\n{sql[insert_pos:]}"


def build_chart(df: pd.DataFrame) -> alt.Chart | None:
    if df.empty:
        return None
    chart_df = df.copy()
    if "service_date_mst" in chart_df.columns:
        chart_df["service_date_mst"] = pd.to_datetime(chart_df["service_date_mst"], errors="coerce")
    if {"route_id", "avg_delay_ratio"} <= set(chart_df.columns):
        return (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("route_id:N", sort="-y"),
                y="avg_delay_ratio:Q",
                tooltip=list(chart_df.columns),
            )
        )
    if {"service_date_mst", "pct_on_time"} <= set(chart_df.columns):
        if "route_id" in chart_df.columns:
            color_field = "route_id"
        elif "stop_id" in chart_df.columns:
            color_field = "stop_id"
        else:
            color_field = None
        chart = (
            alt.Chart(chart_df.dropna(subset=["service_date_mst", "pct_on_time"]))
            .mark_line()
            .encode(
                x="service_date_mst:T",
                y="pct_on_time:Q",
                tooltip=list(chart_df.columns),
            )
        )
        if color_field:
            chart = chart.encode(color=f"{color_field}:N")
        return chart
    return None


def initialize_session_state() -> None:
    defaults = {
        "generated_sql": None,
        "sql_error": None,
        "explanation": "",
        "results_df": None,
        "results_stats": None,
        "run_error": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


models = load_allowed_models()
allowlist = set(models.keys())
_allowed_projects: set[str] = set()
_allowed_datasets: set[str] = set()
for info in models.values():
    parts = [segment.strip("`") for segment in info.fq_name.split(".") if segment]
    if len(parts) >= 3:
        _allowed_projects.add(parts[-3])
    if len(parts) >= 2:
        _allowed_datasets.add(parts[-2])
if not _allowed_projects and settings.GCP_PROJECT_ID:
    _allowed_projects.add(settings.GCP_PROJECT_ID)
if not _allowed_datasets and settings.BQ_DATASET_MART:
    _allowed_datasets.add(settings.BQ_DATASET_MART)


def build_guardrail_config(engine_name: str) -> GuardrailConfig:
    extra: dict[str, set[str]] = {}
    if engine_name == "bigquery":
        extra["allowed_projects"] = _allowed_projects
        extra["allowed_datasets"] = _allowed_datasets
    return GuardrailConfig(allowed_models=allowlist, engine=engine_name, **extra)


schema_brief = build_schema_brief(models)

initialize_session_state()

with st.sidebar:
    st.header("Controls")
    engine = st.radio(
        "Engine",
        ["duckdb", "bigquery"],
        index=0 if settings.ENGINE == "duckdb" else 1,
    )
    today = date.today()
    min_available, max_available = load_service_date_range()
    if min_available and max_available:
        default_start = max(min_available, today - timedelta(days=30))
        default_end = min(max_available, today)
        if default_start > default_end:
            default_start = default_end = min_available
        date_range = st.date_input(
            "Service date range",
            value=(default_start, default_end),
            min_value=min_available,
            max_value=max_available,
        )
        st.caption(f"Available service dates: {min_available} → {max_available}")
    else:
        default_range = (today - timedelta(days=30), today)
        date_range = st.date_input("Service date range", value=default_range)
        st.caption("Available service dates: unavailable")
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range
    routes = st.multiselect("Routes", options=load_route_options())
    stop_search = st.text_input("Stop ID", placeholder="e.g., 12345")
    weather_bins = st.multiselect("Weather bins", options=load_weather_bins())

    st.markdown("---")
    st.subheader("Freshness")
    st.caption("BigQuery dbt build")
    st.write(read_bigquery_freshness())
    st.caption("DuckDB sync")
    st.write(read_duckdb_freshness())

filters = {
    "start_date": start_date.isoformat() if start_date else None,
    "end_date": end_date.isoformat() if end_date else None,
    "routes": routes,
    "stop_id": stop_search,
    "weather": weather_bins,
}

question = st.text_area(
    "Ask a question",
    placeholder="e.g., Worst 10 routes in snow over the last 30 days",
)

generate_clicked = st.button("Generate SQL", type="primary")
if generate_clicked:
    st.session_state["sql_error"] = None
    st.session_state["generated_sql"] = None
    st.session_state["explanation"] = ""
    if not question.strip():
        st.session_state["sql_error"] = "Please enter a question before generating SQL."
    else:
        prompt = build_prompt(question, filters, schema_brief)
        try:
            llm_output = call_provider(prompt)
        except NotImplementedError as exc:
            st.session_state["sql_error"] = str(exc)
            llm_output = None
        if llm_output:
            candidate_sql = llm_output.get("sql", "")
            candidate_sql = add_filter_clauses(candidate_sql, filters)
            try:
                config = build_guardrail_config(engine)
                sanitized_sql = sanitize_sql(candidate_sql, config)
                sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
                st.session_state["generated_sql"] = sanitized_sql
                st.session_state["edited_sql"] = sanitized_sql
                st.session_state["sanitized_sql"] = sanitized_sql
                st.session_state["explanation"] = llm_output.get("explanation", "")
                st.session_state["model_names"] = sorted(models.keys())
                st.session_state["bq_est_bytes_preview"] = None
            except SqlValidationError as exc:
                st.session_state["sql_error"] = str(exc)

if st.session_state.get("sql_error"):
    st.error(st.session_state["sql_error"])

if st.session_state.get("generated_sql"):
    st.subheader("Generated SQL")
    default_sql = st.session_state.get("edited_sql", st.session_state["generated_sql"])
    edited_sql = st.text_area(
        "SQL (editable)",
        value=default_sql,
        height=240,
    )
    st.session_state["edited_sql"] = edited_sql
    try:
        config_preview = build_guardrail_config(engine)
        sanitized = sanitize_sql(edited_sql, config_preview)
        sanitized = adapt_sql_for_engine(sanitized, engine, models)
        st.session_state["sanitized_sql"] = sanitized
        st.session_state["sql_error"] = None
        if engine == "bigquery":
            try:
                estimate_stats = bigquery_engine.estimate(sanitized)
                st.session_state["bq_est_bytes_preview"] = estimate_stats["bq_est_bytes"]
            except Exception as exc:  # pragma: no cover - interactive warning
                st.session_state["bq_est_bytes_preview"] = None
                st.warning(f"Dry-run estimate unavailable: {exc}")
        else:
            st.session_state["bq_est_bytes_preview"] = None
    except SqlValidationError as exc:
        st.session_state["sanitized_sql"] = None
        st.session_state["bq_est_bytes_preview"] = None
        st.session_state["sql_error"] = str(exc)
    if st.session_state.get("explanation"):
        st.info(st.session_state["explanation"])
    if engine == "bigquery" and st.session_state.get("bq_est_bytes_preview") is not None:
        st.caption(
            f"Estimated BigQuery bytes processed: {human_readable_bytes(st.session_state['bq_est_bytes_preview'])} (MAX {human_readable_bytes(int(os.getenv('MAX_BYTES_BILLED', '2000000000')))})."
        )

run_clicked = st.button("Run")

if run_clicked and st.session_state.get("generated_sql"):
    sql_to_run = st.session_state.get("edited_sql", st.session_state["generated_sql"])
    try:
        config_preview = build_guardrail_config(engine)
        sanitized_sql = sanitize_sql(sql_to_run, config_preview)
        sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
        st.session_state["sanitized_sql"] = sanitized_sql
    except SqlValidationError as exc:
        st.session_state["run_error"] = str(exc)
        st.session_state["results_df"] = None
        st.session_state["results_stats"] = None
    else:
        engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
        cached = query_cache.get(engine, sanitized_sql)
        try:
            cache_hit = False
            latency_ms = 0.0
            if cached:
                stats, df = cached
                cache_hit = True
            else:
                start_time = time.monotonic()
                stats, df = engine_module.execute(sanitized_sql)
                latency_ms = (time.monotonic() - start_time) * 1000
                query_cache.set(engine, sanitized_sql, (stats, df))
            log_query(
                engine=engine,
                rows=len(df),
                latency_ms=latency_ms,
                models=st.session_state.get("model_names", allowlist),
                sql=sanitized_sql,
                question=question,
                cache_hit=cache_hit,
                bq_est_bytes=stats.get("bq_est_bytes") if isinstance(stats, dict) else None,
            )
            st.session_state["results_df"] = df
            st.session_state["results_stats"] = stats
            st.session_state["run_error"] = None
        except Exception as exc:
            st.session_state["run_error"] = str(exc)
            st.session_state["results_df"] = None
            st.session_state["results_stats"] = None
elif run_clicked:
    st.session_state["run_error"] = "SQL did not pass validation; adjust your query and try again."

if st.session_state.get("run_error"):
    st.error(f"Query failed: {st.session_state['run_error']}")

results_df: pd.DataFrame | None = st.session_state.get("results_df")
results_stats = st.session_state.get("results_stats")

if results_stats:
    st.subheader("Execution Stats")
    st.json(results_stats)

if results_df is not None:
    st.subheader("Results")
    st.dataframe(results_df, use_container_width=True)
    chart = build_chart(results_df)
    if chart:
        st.altair_chart(chart, use_container_width=True)
    csv_data = results_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", csv_data, file_name="whylinedenver_results.csv", mime="text/csv"
    )
