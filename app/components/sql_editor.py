"""SQL editor component (Step 2) - Review, edit, and validate SQL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# Add src to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Import from app utils (add app directory to path if needed)
import sys as _sys
from pathlib import Path as _Path

from whylinedenver.engines import bigquery_engine
from whylinedenver.llm import adapt_sql_for_engine
from whylinedenver.semantics.dbt_artifacts import ModelInfo
from whylinedenver.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

if str(_Path(__file__).parent.parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
from utils.formatting import human_readable_bytes


def render(
    engine: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> None:
    """
    Render Step 2: SQL editor with validation and execution.

    Args:
        engine: Selected engine (duckdb or bigquery)
        models: Allowed dbt models
        guardrail_config: Guardrail configuration for validation
    """
    if not st.session_state.get("generated_sql"):
        st.info("👆 Generate SQL from a question to continue")
        return

    st.markdown("### Step 2: Review & Edit SQL")

    if st.session_state.get("sql_cache_hit"):
        st.info("⚡ Reused cached SQL for this question.")

    if st.session_state.get("explanation"):
        with st.expander("Query Explanation", expanded=False):
            st.info(st.session_state["explanation"])

    default_sql = st.session_state.get("edited_sql", st.session_state["generated_sql"])
    edited_sql = st.text_area(
        "SQL Query (editable)",
        value=default_sql,
        height=240,
        help="Edit the SQL if needed. Changes are validated automatically.",
    )
    st.session_state["edited_sql"] = edited_sql

    # Real-time validation
    try:
        sanitized = sanitize_sql(edited_sql, guardrail_config)
        sanitized = adapt_sql_for_engine(sanitized, engine, models)
        st.session_state["sanitized_sql"] = sanitized
        st.session_state["sql_error"] = None

        # Show validation success
        st.success("✓ SQL validated successfully")

        # BigQuery estimate
        if engine == "bigquery":
            try:
                estimate_stats = bigquery_engine.estimate(sanitized)
                st.session_state["bq_est_bytes_preview"] = estimate_stats["bq_est_bytes"]
                st.info(
                    f"📊 Estimated bytes: {human_readable_bytes(st.session_state['bq_est_bytes_preview'])} "
                    f"(Max allowed: {human_readable_bytes(int(os.getenv('MAX_BYTES_BILLED', '2000000000')))})"
                )
            except Exception as exc:  # pragma: no cover - interactive warning
                st.session_state["bq_est_bytes_preview"] = None
                st.warning(f"⚠️ Dry-run estimate unavailable: {exc}")
        else:
            st.session_state["bq_est_bytes_preview"] = None

    except SqlValidationError as exc:
        st.session_state["sanitized_sql"] = None
        st.session_state["bq_est_bytes_preview"] = None
        st.session_state["sql_error"] = str(exc)
        st.error(f"❌ SQL Validation Error: {exc}")

    st.markdown("---")
