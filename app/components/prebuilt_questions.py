"""Prebuilt questions component - ready-made queries."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Add src to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from whylinedenver.llm import adapt_sql_for_engine
from whylinedenver.semantics.dbt_artifacts import ModelInfo
from whylinedenver.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

# ═══════════════════════════════════════════════════════════════════════════
# PREBUILT QUESTIONS - Fast demos and guardrails-friendly starting points
# ═══════════════════════════════════════════════════════════════════════════
PREBUILT = [
    (
        "Worst 10 routes (last 30 days)",
        "SELECT route_id, AVG(pct_on_time) AS avg_pct_on_time "
        "FROM mart_reliability_by_route_day "
        "WHERE service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY) "
        "GROUP BY route_id "
        "ORDER BY avg_pct_on_time ASC "
        "LIMIT 10",
    ),
    (
        "Stops with highest crash exposure",
        "SELECT stop_id, crash_250m_cnt "
        "FROM mart_crash_proximity_by_stop "
        "ORDER BY crash_250m_cnt DESC "
        "LIMIT 20",
    ),
    (
        "Where snow hurts reliability most",
        "SELECT route_id, delta_pct_on_time "
        "FROM mart_weather_impacts "
        "WHERE precip_bin IN ('mod', 'heavy') "
        "ORDER BY delta_pct_on_time ASC "
        "LIMIT 10",
    ),
    (
        "Equity gaps (high vulnerability, low reliability)",
        "SELECT p.stop_id, v.vuln_score_0_100, r.reliability_score_0_100, p.priority_score "
        "FROM mart_priority_hotspots p "
        "JOIN mart_vulnerability_by_stop v USING(stop_id) "
        "JOIN ("
        "  SELECT stop_id, 100 * (1 - AVG(pct_on_time)) AS reliability_score_0_100 "
        "  FROM mart_reliability_by_stop_hour "
        "  WHERE service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 35 DAY) "
        "  GROUP BY stop_id"
        ") r USING(stop_id) "
        "ORDER BY p.priority_score DESC "
        "LIMIT 20",
    ),
]


def render(
    engine: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> None:
    """
    Render prebuilt question buttons that load SQL directly into the editor.

    Args:
        engine: Selected engine (duckdb or bigquery)
        models: Allowed dbt models
        guardrail_config: Guardrail configuration for validation
    """
    st.markdown("### Prebuilt Questions")
    st.caption("Click a button to load a ready-made query into the SQL editor")

    cols = st.columns(2)
    for i, (label, sql) in enumerate(PREBUILT):
        # Explicitly mark as secondary to pick up scoped CSS that keeps labels on one line
        if cols[i % 2].button(
            label,
            use_container_width=True,
            key=f"prebuilt_{i}",
            type="secondary",
        ):
            # Validate and adapt SQL for current engine
            try:
                sanitized_sql = sanitize_sql(sql, guardrail_config)
                sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)

                # Set session state to skip Step 1 and go directly to Step 2
                st.session_state["generated_sql"] = sanitized_sql
                st.session_state["edited_sql"] = sanitized_sql
                st.session_state["sanitized_sql"] = sanitized_sql
                st.session_state["explanation"] = f"Prebuilt query: {label}"
                st.session_state["model_names"] = sorted(models.keys())
                st.session_state["sql_error"] = None
                st.session_state["results_df"] = None
                st.session_state["results_stats"] = None
                st.session_state["run_error"] = None
                st.session_state["bq_est_bytes_preview"] = None
                st.rerun()
            except SqlValidationError as exc:
                st.error(f"❌ Prebuilt query validation failed: {exc}")

    st.markdown("---")
