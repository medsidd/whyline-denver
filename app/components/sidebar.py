"""Sidebar component with filters and controls."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

# Add src to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Import from app utils (add app directory to path if needed)
import sys as _sys
from pathlib import Path as _Path

from whylinedenver.config import settings

if str(_Path(__file__).parent.parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
from utils.data_loaders import (
    load_route_options,
    load_service_date_range,
    load_weather_bins,
    read_bigquery_freshness,
    read_duckdb_freshness,
)


def _freshness_badge(label: str, value: str, variant: str) -> None:
    """Render a styled freshness badge in the sidebar."""
    st.markdown(
        f"""
        <div class="status-badge status-badge--{variant}">
            <span class="status-badge__label">{label}</span>
            <span class="status-badge__value">{value}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> tuple[str, dict[str, Any]]:
    """
    Render sidebar with engine selector, filters, and freshness indicators.

    Returns:
        (engine, filters_dict): Selected engine and filter values
    """
    with st.sidebar:
        st.header("Freshness")
        bq_freshness = read_bigquery_freshness()
        duckdb_freshness = read_duckdb_freshness()
        _freshness_badge(
            "dbt build (BigQuery)",
            bq_freshness,
            "primary" if bq_freshness != "Unavailable" else "warning",
        )
        _freshness_badge(
            "DuckDB sync",
            duckdb_freshness,
            "accent" if duckdb_freshness != "Unavailable" else "warning",
        )
        st.caption("BigQuery: full corpus  \nDuckDB: ≈90 days cached for fast local exploration.")

        st.markdown('<hr class="section-separator" />', unsafe_allow_html=True)
        st.header("Controls")

        engine = st.radio(
            "Engine",
            ["duckdb", "bigquery"],
            index=0 if settings.ENGINE == "duckdb" else 1,
            format_func=lambda value: "DuckDB" if value == "duckdb" else "BigQuery",
            help="Switch between DuckDB (local, fast) and BigQuery (cloud, up-to-date)",
        )

        # Detect engine change and reset Step 2 & 3 (but preserve question in Step 1)
        if "last_engine" not in st.session_state:
            st.session_state["last_engine"] = engine
        elif st.session_state["last_engine"] != engine:
            # Engine changed - reset SQL and results but keep the question
            st.session_state["generated_sql"] = None
            st.session_state["edited_sql"] = None
            st.session_state["sanitized_sql"] = None
            st.session_state["explanation"] = ""
            st.session_state["query_params"] = None  # Clear query params (optimized)
            st.session_state["results_stats"] = None
            st.session_state["run_error"] = None
            st.session_state["sql_error"] = None
            st.session_state["bq_est_bytes_preview"] = None
            st.session_state["last_engine"] = engine

        # Date range filter
        today = date.today()
        min_available, max_available, date_error = load_service_date_range(engine)

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
            if date_error:
                st.error(f"⚠️ Failed to load date range: {date_error}")
            else:
                st.caption("Available service dates: unavailable")

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range

        # Routes filter
        route_options, route_error = load_route_options(engine)
        routes = st.multiselect("Routes", options=route_options)
        if route_error:
            st.error(f"⚠️ Failed to load routes: {route_error}")

        # Stop ID filter
        stop_search = st.text_input("Stop ID", placeholder="e.g., 12345")

        # Weather bins filter
        weather_options, weather_error = load_weather_bins(engine)
        weather_bins = st.multiselect("Weather bins", options=weather_options)
        if weather_error:
            st.warning(f"⚠️ Weather bins error: {weather_error}")

        # Active filters summary
        st.markdown("---")
        st.subheader("Active Filters")
        active_filters = []
        if start_date and end_date:
            active_filters.append(f"📅 {start_date} → {end_date}")
        if routes:
            route_summary = ", ".join(routes[:3])
            if len(routes) > 3:
                route_summary += f" +{len(routes)-3} more"
            active_filters.append(f"🚌 Routes: {route_summary}")
        if stop_search.strip():
            active_filters.append(f"🚏 Stop: {stop_search.strip()}")
        if weather_bins:
            weather_summary = ", ".join(weather_bins)
            active_filters.append(f"🌦️ Weather: {weather_summary}")

        if active_filters:
            for filter_text in active_filters:
                st.caption(filter_text)
        else:
            st.caption("_No filters applied_")

    # Build filters dictionary
    filters = {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "routes": routes,
        "stop_id": stop_search,
        "weather": weather_bins,
    }

    return engine, filters
