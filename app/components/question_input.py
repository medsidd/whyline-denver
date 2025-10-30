"""Question input component (Step 1) - Natural language to SQL generation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

# Add src to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Import from app utils (add app directory to path if needed)
import sys
from pathlib import Path as _Path

from whylinedenver.llm import adapt_sql_for_engine, build_prompt, call_provider
from whylinedenver.logs import prompt_cache
from whylinedenver.semantics.dbt_artifacts import ModelInfo
from whylinedenver.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

if str(_Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(_Path(__file__).parent.parent))
from utils.filters import add_filter_clauses


def render(
    engine: str,
    filters: Mapping[str, Any],
    schema_brief: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> str:
    """
    Render Step 1: Natural language question input and SQL generation.

    Args:
        engine: Selected engine (duckdb or bigquery)
        filters: Filter values from sidebar
        schema_brief: Schema description for LLM
        models: Allowed dbt models
        guardrail_config: Guardrail configuration for validation

    Returns:
        The user's question text
    """
    st.markdown("### Step 1: Ask Your Question")
    question = st.text_area(
        "Enter your natural language question",
        placeholder="e.g., Worst 10 routes in snow over the last 30 days",
        help="Ask questions about transit reliability, delays, or weather impacts",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        generate_clicked = st.button("Generate SQL", type="primary", use_container_width=True)
    with col2:
        if st.session_state.get("generated_sql"):
            st.success("✓ SQL generated successfully")

    if generate_clicked:
        st.session_state["sql_error"] = None
        st.session_state["generated_sql"] = None
        st.session_state["explanation"] = ""
        st.session_state["query_params"] = None  # Clear query params (optimized)
        st.session_state["results_stats"] = None
        st.session_state["run_error"] = None
        st.session_state["sql_cache_hit"] = False

        if not question.strip():
            st.session_state["sql_error"] = "Please enter a question before generating SQL."
        else:
            with st.spinner("Generating SQL query..."):
                prompt = build_prompt(question, filters, schema_brief)
                provider = os.getenv("LLM_PROVIDER", "stub").lower()
                cache_entry = prompt_cache.get(provider, engine, question, filters)

                if cache_entry:
                    cached_sql = cache_entry.get("sql", "")
                    cached_explanation = cache_entry.get("explanation", "")
                    try:
                        sanitized_sql = sanitize_sql(cached_sql, guardrail_config)
                        sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
                    except SqlValidationError as exc:
                        st.session_state["sql_error"] = str(exc)
                    else:
                        st.session_state["generated_sql"] = sanitized_sql
                        st.session_state["edited_sql"] = sanitized_sql
                        st.session_state["sanitized_sql"] = sanitized_sql
                        st.session_state["explanation"] = cached_explanation
                        st.session_state["model_names"] = sorted(models.keys())
                        st.session_state["bq_est_bytes_preview"] = None
                        st.session_state["sql_cache_hit"] = True
                else:
                    try:
                        llm_output = call_provider(prompt)
                    except NotImplementedError as exc:
                        st.session_state["sql_error"] = str(exc)
                        llm_output = None
                    except Exception as exc:  # pragma: no cover - surface LLM runtime errors
                        st.session_state["sql_error"] = f"LLM provider error: {exc}"
                        llm_output = None

                    if llm_output:
                        candidate_sql = llm_output.get("sql", "")
                        candidate_sql = add_filter_clauses(candidate_sql, filters)
                        try:
                            sanitized_sql = sanitize_sql(candidate_sql, guardrail_config)
                            sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
                            explanation = llm_output.get("explanation", "")
                            st.session_state["generated_sql"] = sanitized_sql
                            st.session_state["edited_sql"] = sanitized_sql
                            st.session_state["sanitized_sql"] = sanitized_sql
                            st.session_state["explanation"] = explanation
                            st.session_state["model_names"] = sorted(models.keys())
                            st.session_state["bq_est_bytes_preview"] = None
                            prompt_cache.set(
                                provider,
                                engine,
                                question,
                                filters,
                                {"sql": sanitized_sql, "explanation": explanation},
                            )
                        except SqlValidationError as exc:
                            st.session_state["sql_error"] = str(exc)

    if st.session_state.get("sql_error"):
        st.error(st.session_state["sql_error"])

    st.markdown("---")

    return question
