"""Results viewer component (Step 3) - Display results, charts, and download."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

# Add src to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Import from app components (add app directory to path if needed)
import sys as _sys
from pathlib import Path as _Path

from whylinedenver.engines import bigquery_engine, duckdb_engine
from whylinedenver.llm import adapt_sql_for_engine
from whylinedenver.logs import log_query, query_cache
from whylinedenver.semantics.dbt_artifacts import ModelInfo
from whylinedenver.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

if str(_Path(__file__).parent.parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
from components.charts import build_chart, build_map


def render(
    engine: str,
    question: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
    allowlist: set[str],
) -> None:
    """
    Render Step 3: Query execution results with charts and download.

    Args:
        engine: Selected engine (duckdb or bigquery)
        question: User's original question
        models: Allowed dbt models
        guardrail_config: Guardrail configuration for validation
        allowlist: Set of allowed model names
    """
    if not st.session_state.get("generated_sql"):
        return

    st.markdown("### Step 3: Results")

    # Run button
    col1, col2 = st.columns([1, 5])
    with col1:
        run_clicked = st.button(
            "Run Query",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.get("sql_error") is not None,
        )
    with col2:
        if st.session_state.get("results_df") is not None:
            st.success(
                f"✓ Query executed successfully ({len(st.session_state['results_df'])} rows)"
            )

    if run_clicked:
        sql_to_run = st.session_state.get("edited_sql", st.session_state["generated_sql"])
        try:
            sanitized_sql = sanitize_sql(sql_to_run, guardrail_config)
            sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
            st.session_state["sanitized_sql"] = sanitized_sql
        except SqlValidationError as exc:
            st.session_state["run_error"] = str(exc)
            st.session_state["results_df"] = None
            st.session_state["results_stats"] = None
        else:
            with st.spinner("Executing query..."):
                engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
                cached = query_cache.get(engine, sanitized_sql)
                try:
                    cache_hit = False
                    latency_ms = 0.0
                    if cached:
                        stats, df = cached
                        cache_hit = True
                        st.info("⚡ Results loaded from cache")
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

    if st.session_state.get("run_error"):
        st.error(f"❌ Query failed: {st.session_state['run_error']}")

    results_df: pd.DataFrame | None = st.session_state.get("results_df")
    results_stats = st.session_state.get("results_stats")

    if results_df is not None:
        # Execution stats in expander
        if results_stats:
            with st.expander("Execution Statistics", expanded=False):
                st.json(results_stats)

        # Results table
        st.dataframe(results_df, use_container_width=True)

        # Visualization
        chart = build_chart(results_df)
        if chart:
            st.altair_chart(chart, use_container_width=True)

        # Map visualization
        engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
        hotspot_map = build_map(results_df, engine_module)
        if hotspot_map:
            st.pydeck_chart(hotspot_map)

        # Download button
        csv_data = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv_data,
            file_name="whylinedenver_results.csv",
            mime="text/csv",
            use_container_width=True,
        )
    elif not st.session_state.get("run_error"):
        st.info("👆 Run the query to see results")
