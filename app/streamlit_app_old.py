# ruff: noqa: E402,I001
from __future__ import annotations

import base64
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
from whylinedenver.logs import log_query, prompt_cache, query_cache  # noqa: E402
from whylinedenver.semantics.dbt_artifacts import DbtArtifacts, ModelInfo  # noqa: E402
from whylinedenver.sql_guardrails import (  # noqa: E402
    GuardrailConfig,
    SqlValidationError,
    sanitize_sql,
)
from whylinedenver.sync.state_store import load_sync_state  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# BRAND IDENTITY - Vintage Transit Palette
# ═══════════════════════════════════════════════════════════════════════════
BRAND_PRIMARY = os.getenv("APP_PRIMARY_COLOR", "#87a7b3")  # Dusty Sky Blue
BRAND_ACCENT = os.getenv("APP_ACCENT_COLOR", "#d4a574")  # Vintage Gold
BRAND_SUCCESS = os.getenv("APP_SUCCESS_COLOR", "#a3b88c")  # Sage Green
BRAND_WARNING = os.getenv("APP_WARNING_COLOR", "#e8b863")  # Soft Amber
BRAND_ERROR = os.getenv("APP_ERROR_COLOR", "#c77f6d")  # Terra Cotta
BRAND_NAME = os.getenv("APP_BRAND_NAME", "WhyLine Denver")
BRAND_TAGLINE = os.getenv("APP_TAGLINE", "Ask anything about Denver transit — in your own words")

# Chart color palette (5-color sequential for data viz)
CHART_COLORS = [BRAND_PRIMARY, BRAND_SUCCESS, BRAND_ACCENT, BRAND_WARNING, BRAND_ERROR]

st.set_page_config(
    page_title=f"{BRAND_NAME} — Transit Analytics",
    page_icon=str(Path(__file__).parent / "assets" / "whylinedenver-logo@512.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM THEMING - Hide Streamlit branding, apply vintage transit aesthetic
# ═══════════════════════════════════════════════════════════════════════════
def inject_custom_css() -> None:
    """Apply heavy custom CSS to override Streamlit defaults and create retro aesthetic."""
    st.markdown(
        f"""
        <style>
        /* Import Google Fonts - Space Grotesk (headers) & Inter (body) */
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

        /* ═══ GLOBAL RESETS & BASE STYLES ═══ */
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #e8d5c4;
            background: #232129;
        }}

        /* Hide Streamlit branding */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}

        /* Remove extra padding */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 100%;
        }}

        /* ═══ TYPOGRAPHY - STRONGER RETRO ═══ */
        h1, h2, h3, h4, h5, h6 {{
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 700;
            letter-spacing: -0.03em;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}

        h1 {{
            font-size: 3rem;
            color: {BRAND_PRIMARY};
            margin-bottom: 0.5rem;
            font-weight: 800;
        }}

        h2 {{
            font-size: 2rem;
            color: {BRAND_ACCENT};
            margin-top: 2rem;
            margin-bottom: 1rem;
            font-weight: 700;
        }}

        h3 {{
            font-size: 1.5rem;
            color: {BRAND_ACCENT};
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
            font-weight: 700;
        }}

        /* ═══ BUTTONS - MORE RETRO PUNCH ═══ */
        .stButton > button {{
            background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 100%);
            color: #1a171d;
            border: 3px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 0.75rem 2rem;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 1.1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            white-space: nowrap;
            transition: all 0.3s ease;
            box-shadow:
                0 6px 20px rgba(135, 167, 179, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
        }}

        .stButton > button:hover {{
            transform: translateY(-3px);
            color: #0a0609 !important;
            box-shadow:
                0 10px 30px rgba(135, 167, 179, 0.5),
                inset 0 1px 0 rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.3);
        }}

        .stButton > button:active {{
            transform: translateY(-1px);
            box-shadow:
                0 4px 12px rgba(135, 167, 179, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
        }}

        /* Primary button (Generate SQL, Run Query) - EXTRA RETRO */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {BRAND_ACCENT} 0%, {BRAND_WARNING} 100%);
            color: #1a171d;
            font-weight: 800;
            border: 3px solid rgba(255, 255, 255, 0.25);
            box-shadow:
                0 8px 24px rgba(212, 165, 116, 0.4),
                inset 0 2px 0 rgba(255, 255, 255, 0.3),
                inset 0 -2px 0 rgba(0, 0, 0, 0.2);
        }}

        .stButton > button[kind="primary"]:hover {{
            box-shadow:
                0 12px 36px rgba(212, 165, 116, 0.6),
                inset 0 2px 0 rgba(255, 255, 255, 0.4),
                inset 0 -2px 0 rgba(0, 0, 0, 0.2);
        }}

        /* ═══ INPUT FIELDS - RETRO STYLE ═══ */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stSelectbox > div > div > select,
        .stMultiselect > div > div {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            color: #e8d5c4 !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 500;
            transition: all 0.2s ease;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
        }}

        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {{
            border-color: {BRAND_PRIMARY} !important;
            box-shadow:
                0 0 0 4px rgba(135, 167, 179, 0.2) !important,
                inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* ═══ SIDEBAR - CONSISTENT INPUT STYLING ═══ */
        [data-testid="stSidebar"] {{
            background-color: #1a171d;
            border-right: 1px solid #433f4c;
        }}

        [data-testid="stSidebar"] h2 {{
            color: {BRAND_ACCENT};
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
        }}

        /* Make all sidebar inputs look like text boxes */
        [data-testid="stSidebar"] .stSelectbox > div > div,
        [data-testid="stSidebar"] .stMultiSelect > div > div,
        [data-testid="stSidebar"] .stDateInput > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div {{
            background-color: #322e38 !important;
        }}

        [data-testid="stSidebar"] .stSelectbox > div > div > div,
        [data-testid="stSidebar"] .stMultiSelect > div > div > div,
        [data-testid="stSidebar"] .stDateInput > div > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div > input {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            color: #e8d5c4 !important;
            padding: 0.75rem 1rem !important;
            font-weight: 500 !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* Style the dropdown arrows and icons */
        [data-testid="stSidebar"] .stSelectbox svg,
        [data-testid="stSidebar"] .stMultiSelect svg,
        [data-testid="stSidebar"] .stDateInput svg {{
            color: {BRAND_PRIMARY} !important;
        }}

        /* Style multiselect tags */
        [data-testid="stSidebar"] .stMultiSelect span[data-baseweb="tag"] {{
            background-color: {BRAND_PRIMARY} !important;
            color: #1a171d !important;
            border-radius: 6px !important;
            padding: 0.25rem 0.5rem !important;
            font-weight: 600 !important;
        }}

        /* Radio buttons */
        [data-testid="stSidebar"] .stRadio > div {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            padding: 0.75rem 1rem !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* ═══ METRICS & STATUS ═══ */
        .stAlert {{
            border-radius: 8px;
            border-left: 4px solid;
            font-family: 'Inter', sans-serif;
        }}

        .stSuccess {{
            background-color: rgba(163, 184, 140, 0.1);
            border-left-color: {BRAND_SUCCESS};
            color: {BRAND_SUCCESS};
        }}

        .stWarning {{
            background-color: rgba(232, 184, 99, 0.1);
            border-left-color: {BRAND_WARNING};
            color: {BRAND_WARNING};
        }}

        .stError {{
            background-color: rgba(199, 127, 109, 0.1);
            border-left-color: {BRAND_ERROR};
            color: {BRAND_ERROR};
        }}

        .stInfo {{
            background-color: rgba(135, 167, 179, 0.1);
            border-left-color: {BRAND_PRIMARY};
            color: {BRAND_PRIMARY};
        }}

        /* ═══ DATAFRAMES ═══ */
        .stDataFrame {{
            border-radius: 8px;
            overflow: hidden;
        }}

        /* ═══ EXPANDERS ═══ */
        .streamlit-expanderHeader {{
            background-color: #322e38;
            border-radius: 8px;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 500;
            color: {BRAND_ACCENT};
        }}

        /* ═══ DIVIDERS ═══ */
        hr {{
            border-color: #433f4c;
            margin: 2rem 0;
        }}

        /* ═══ CODE BLOCKS (SQL) ═══ */
        code {{
            background-color: #1a171d;
            color: {BRAND_SUCCESS};
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', 'Courier New', monospace;
        }}

        pre {{
            background-color: #1a171d;
            border: 1px solid #433f4c;
            border-radius: 8px;
            padding: 1rem;
        }}

        /* ═══ DOWNLOAD BUTTON ═══ */
        .stDownloadButton > button {{
            background-color: #322e38;
            color: {BRAND_SUCCESS};
            border: 2px solid {BRAND_SUCCESS};
            border-radius: 8px;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 600;
            transition: all 0.3s ease;
        }}

        .stDownloadButton > button:hover {{
            background-color: {BRAND_SUCCESS};
            color: #232129;
        }}

        /* ═══ RADIO BUTTONS ═══ */
        .stRadio > label {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 500;
            color: {BRAND_ACCENT};
        }}

        /* ═══ MULTISELECT TAGS ═══ */
        .stMultiselect span[data-baseweb="tag"] {{
            background-color: {BRAND_PRIMARY} !important;
            color: #232129 !important;
            font-weight: 500;
        }}

        /* ═══ CAPTIONS ═══ */
        .caption {{
            color: #9a8e7e;
            font-size: 0.875rem;
        }}

        /* ═══ HIDE HEADER ANCHOR LINKS ═══ */
        /* Remove Streamlit's automatic header anchor/clip icons */
        h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_branded_header() -> None:
    """Render custom header with logo and tagline - ENHANCED RETRO VERSION."""
    logo_path = Path(__file__).parent / "assets" / "whylinedenver-logo@512.png"

    # Retro rainbow stripe gradient
    stripe_gradient = f"linear-gradient(90deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 25%, {BRAND_SUCCESS} 50%, {BRAND_WARNING} 75%, {BRAND_ERROR} 100%)"

    if logo_path.exists():
        # Encode logo as base64 for embedding
        with open(logo_path, "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()

        # Create image element (no animation)
        img_element = f'<img src="data:image/png;base64,{logo_data}" style="height: 140px; width: auto; filter: drop-shadow(0 6px 16px rgba(0,0,0,0.5));" />'
    else:
        # Fallback: no image
        img_element = ""

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 2.5rem; margin-bottom: 2.5rem; padding: 2.5rem;
                    background: linear-gradient(135deg, rgba(135, 167, 179, 0.15) 0%, rgba(212, 165, 116, 0.12) 100%);
                    border-radius: 16px;
                    border: 4px solid rgba(135, 167, 179, 0.3);
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
                    position: relative;
                    overflow: hidden;">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 6px; background: {stripe_gradient};"></div>
            {img_element}
            <div>
                <h1 style="margin: 0; font-size: 3.5rem; font-weight: 800;
                           background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 100%);
                           -webkit-background-clip: text;
                           -webkit-text-fill-color: transparent;
                           background-clip: text;
                           letter-spacing: -0.03em;
                           line-height: 1.1;">
                    {BRAND_NAME}
                </h1>
                <p style="margin: 0.75rem 0 0 0; color: {BRAND_ACCENT}; font-size: 1.3rem;
                          font-weight: 500; letter-spacing: 0.02em;">
                    {BRAND_TAGLINE}
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Apply theming and render header
inject_custom_css()
render_branded_header()


@st.cache_data
def load_allowed_models() -> dict[str, ModelInfo]:
    artifacts = DbtArtifacts()
    return artifacts.allowed_models()


@st.cache_data
def load_route_options(engine_name: str) -> tuple[list[str], str | None]:
    """Load route options from the selected engine. Returns (routes, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        _, df = engine_module.execute(
            f"SELECT DISTINCT route_id FROM {table_name} "
            "WHERE route_id IS NOT NULL ORDER BY route_id LIMIT 200"
        )
        return df["route_id"].astype(str).tolist(), None
    except Exception as exc:
        return [], str(exc)


@st.cache_data
def load_weather_bins(engine_name: str) -> tuple[list[str], str | None]:
    """Load weather bins from the selected engine. Returns (bins, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        _, df = engine_module.execute(
            f"SELECT DISTINCT precip_bin FROM {table_name} "
            "WHERE precip_bin IS NOT NULL ORDER BY precip_bin"
        )
        return df["precip_bin"].astype(str).tolist(), None
    except Exception as exc:
        return ["none", "rain", "snow"], str(exc)


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
def load_service_date_range(engine_name: str) -> tuple[date | None, date | None, str | None]:
    """Load service date range from the selected engine. Returns (min_date, max_date, error_message)."""
    try:
        engine_module = duckdb_engine if engine_name == "duckdb" else bigquery_engine

        # Qualify table name for BigQuery
        if engine_name == "bigquery":
            table_name = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.mart_reliability_by_route_day`"
        else:
            table_name = "mart_reliability_by_route_day"

        _, df = engine_module.execute(
            f"SELECT MIN(service_date_mst) AS min_date, MAX(service_date_mst) AS max_date "
            f"FROM {table_name}"
        )
        if df.empty:
            return None, None, "No data found in mart_reliability_by_route_day"
        min_timestamp = pd.to_datetime(df.loc[0, "min_date"])
        max_timestamp = pd.to_datetime(df.loc[0, "max_date"])
        if pd.isna(min_timestamp) or pd.isna(max_timestamp):
            return None, None, "Date values are null or invalid"
        min_date = min_timestamp.date()
        max_date = max_timestamp.date()
        return min_date, max_date, None
    except Exception as exc:
        return None, None, str(exc)


@st.cache_data(ttl=60)
def _load_sync_state_payload() -> dict[str, Any] | None:
    """Load sync_state with a short cache to avoid repeated GCS reads."""
    return load_sync_state()


def read_duckdb_freshness() -> str:
    """Read DuckDB sync timestamp from sync_state.json (preferring GCS)."""
    payload = _load_sync_state_payload()
    if not payload:
        return "Unavailable"
    ts = payload.get("duckdb_synced_at_utc") or payload.get("refreshed_at_utc")  # Backward compat
    return _format_timestamp(ts)


def read_bigquery_freshness() -> str:
    """Read BigQuery update timestamp from sync_state.json."""
    payload = _load_sync_state_payload()
    if payload:
        ts = payload.get("bigquery_updated_at_utc")
        if ts:
            return _format_timestamp(ts)

    try:
        # Fallback: read from dbt run_results.json if not in sync_state
        dbt_path = Path("dbt/target/run_results.json")
        if dbt_path.exists():
            dbt_payload = json.loads(dbt_path.read_text(encoding="utf-8"))
            metadata = dbt_payload.get("metadata", {})
            generated_at = metadata.get("generated_at")
            if generated_at:
                return _format_timestamp(generated_at)

        return "Unavailable"
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
    """Build an appropriate chart based on available columns with brand colors."""
    if df.empty or len(df) == 0:
        return None

    chart_df = df.copy()

    # Convert date columns
    if "service_date_mst" in chart_df.columns:
        chart_df["service_date_mst"] = pd.to_datetime(chart_df["service_date_mst"], errors="coerce")

    # Limit to top/bottom entries for readability
    max_categories = 15

    # Chart 1: Route-based delay ratio bar chart
    if {"route_id", "avg_delay_ratio"} <= set(chart_df.columns):
        # Take top entries by delay ratio
        plot_df = chart_df.nlargest(max_categories, "avg_delay_ratio")

        return (
            alt.Chart(plot_df)
            .mark_bar(cornerRadius=4)
            .encode(
                x=alt.X("route_id:N", sort="-y", title="Route ID", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y(
                    "avg_delay_ratio:Q", title="Average Delay Ratio", scale=alt.Scale(zero=True)
                ),
                color=alt.Color(
                    "avg_delay_ratio:Q",
                    scale=alt.Scale(
                        domain=[plot_df["avg_delay_ratio"].min(), plot_df["avg_delay_ratio"].max()],
                        range=[BRAND_SUCCESS, BRAND_WARNING, BRAND_ERROR],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("route_id:N", title="Route"),
                    alt.Tooltip("avg_delay_ratio:Q", title="Delay Ratio", format=".3f"),
                ]
                + [
                    alt.Tooltip(f"{col}:Q", format=".2f")
                    for col in chart_df.columns
                    if col not in ["route_id", "avg_delay_ratio"]
                    and pd.api.types.is_numeric_dtype(chart_df[col])
                ],
            )
            .properties(title="Top Routes by Delay Ratio", height=400)
            .configure_axis(labelColor="#c4b5a0", titleColor="#e8d5c4", gridColor="#433f4c")
            .configure_title(color=BRAND_ACCENT, fontSize=18, font="Space Grotesk", anchor="start")
        )

    # Chart 2: Time series of on-time percentage
    if {"service_date_mst", "pct_on_time"} <= set(chart_df.columns):
        clean_df = chart_df.dropna(subset=["service_date_mst", "pct_on_time"])

        if "route_id" in clean_df.columns:
            color_field = "route_id:N"
            # Limit to top routes by average on-time percentage
            top_routes = clean_df.groupby("route_id")["pct_on_time"].mean().nlargest(5).index
            clean_df = clean_df[clean_df["route_id"].isin(top_routes)]
        elif "stop_id" in clean_df.columns:
            color_field = "stop_id:N"
            # Limit to top stops
            top_stops = clean_df.groupby("stop_id")["pct_on_time"].mean().nlargest(5).index
            clean_df = clean_df[clean_df["stop_id"].isin(top_stops)]
        else:
            color_field = None

        chart = (
            alt.Chart(clean_df)
            .mark_line(point=True, strokeWidth=3, size=80)
            .encode(
                x=alt.X("service_date_mst:T", title="Date"),
                y=alt.Y("pct_on_time:Q", title="On-Time %", scale=alt.Scale(domain=[0, 100])),
                tooltip=[
                    alt.Tooltip("service_date_mst:T", title="Date", format="%Y-%m-%d"),
                    alt.Tooltip("pct_on_time:Q", title="On-Time %", format=".1f"),
                ]
                + (
                    [
                        alt.Tooltip(
                            color_field.split(":")[0],
                            title=color_field.split(":")[0].replace("_", " ").title(),
                        )
                    ]
                    if color_field
                    else []
                ),
            )
            .properties(title="On-Time Performance Over Time", height=400)
            .configure_axis(labelColor="#c4b5a0", titleColor="#e8d5c4", gridColor="#433f4c")
            .configure_title(color=BRAND_ACCENT, fontSize=18, font="Space Grotesk", anchor="start")
        )

        if color_field:
            chart = chart.encode(
                color=alt.Color(
                    color_field,
                    title=color_field.split(":")[0].replace("_", " ").title(),
                    scale=alt.Scale(range=CHART_COLORS[:5]),
                )
            )
        else:
            # Single line - use primary brand color
            chart = chart.mark_line(point=True, strokeWidth=3, size=80, color=BRAND_PRIMARY)

        return chart

    # Chart 3: Generic bar chart for any numeric column
    numeric_cols = [col for col in chart_df.columns if pd.api.types.is_numeric_dtype(chart_df[col])]
    categorical_cols = [
        col
        for col in chart_df.columns
        if not pd.api.types.is_numeric_dtype(chart_df[col]) and col != "service_date_mst"
    ]

    if len(numeric_cols) > 0 and len(categorical_cols) > 0:
        y_col = numeric_cols[0]
        x_col = categorical_cols[0]

        # Limit categories
        if len(chart_df) > max_categories:
            chart_df = chart_df.nlargest(max_categories, y_col)

        return (
            alt.Chart(chart_df)
            .mark_bar(cornerRadius=4)
            .encode(
                x=alt.X(f"{x_col}:N", sort="-y", title=x_col.replace("_", " ").title()),
                y=alt.Y(
                    f"{y_col}:Q", title=y_col.replace("_", " ").title(), scale=alt.Scale(zero=True)
                ),
                color=alt.Color(
                    f"{y_col}:Q",
                    scale=alt.Scale(
                        domain=[chart_df[y_col].min(), chart_df[y_col].max()],
                        range=[BRAND_PRIMARY, BRAND_ACCENT],
                    ),
                    legend=None,
                ),
                tooltip=list(chart_df.columns),
            )
            .properties(height=400)
            .configure_axis(labelColor="#c4b5a0", titleColor="#e8d5c4", gridColor="#433f4c")
            .configure_title(color=BRAND_ACCENT, fontSize=18, font="Space Grotesk", anchor="start")
        )

    return None


def initialize_session_state() -> None:
    defaults = {
        "generated_sql": None,
        "sql_error": None,
        "explanation": "",
        "results_df": None,
        "results_stats": None,
        "run_error": None,
        "sql_cache_hit": False,
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
        st.session_state["results_df"] = None
        st.session_state["results_stats"] = None
        st.session_state["run_error"] = None
        st.session_state["sql_error"] = None
        st.session_state["bq_est_bytes_preview"] = None
        st.session_state["last_engine"] = engine

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

    route_options, route_error = load_route_options(engine)
    routes = st.multiselect("Routes", options=route_options)
    if route_error:
        st.error(f"⚠️ Failed to load routes: {route_error}")

    stop_search = st.text_input("Stop ID", placeholder="e.g., 12345")

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

    st.markdown("---")
    st.subheader("Freshness")
    st.caption("BigQuery dbt build")
    st.write(read_bigquery_freshness())
    st.caption("DuckDB sync")
    st.write(read_duckdb_freshness())

    st.markdown("---")
    st.subheader("Resources")
    st.markdown("[📚 Model Documentation](https://medsidd.github.io/whyline-denver/)")
    st.caption("Interactive dbt docs with full lineage graphs and column-level metadata")

filters = {
    "start_date": start_date.isoformat() if start_date else None,
    "end_date": end_date.isoformat() if end_date else None,
    "routes": routes,
    "stop_id": stop_search,
    "weather": weather_bins,
}

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

# Render prebuilt question buttons
st.markdown("### Prebuilt Questions")
st.caption("Click a button to load a ready-made query into the SQL editor")

cols = st.columns(2)
for i, (label, sql) in enumerate(PREBUILT):
    if cols[i % 2].button(label, use_container_width=True, key=f"prebuilt_{i}"):
        # Validate and adapt SQL for current engine
        try:
            config = build_guardrail_config(engine)
            sanitized_sql = sanitize_sql(sql, config)
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

# Step 1: Ask Your Question
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
    st.session_state["results_df"] = None
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
                    config = build_guardrail_config(engine)
                    sanitized_sql = sanitize_sql(cached_sql, config)
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
                if llm_output:
                    candidate_sql = llm_output.get("sql", "")
                    candidate_sql = add_filter_clauses(candidate_sql, filters)
                    try:
                        config = build_guardrail_config(engine)
                        sanitized_sql = sanitize_sql(candidate_sql, config)
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

# Step 2: Review & Edit SQL
if st.session_state.get("generated_sql"):
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
        config_preview = build_guardrail_config(engine)
        sanitized = sanitize_sql(edited_sql, config_preview)
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
            config_preview = build_guardrail_config(engine)
            sanitized_sql = sanitize_sql(sql_to_run, config_preview)
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

    st.markdown("---")
else:
    st.info("👆 Generate SQL from a question to continue")

# Step 3: Results
if st.session_state.get("generated_sql"):
    st.markdown("### Step 3: Results")

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

# ═══════════════════════════════════════════════════════════════════════════
# FOOTER - Branding & Attributions
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(
    f"""
    <div style="text-align: center; padding: 2rem 0; color: #9a8e7e; font-size: 0.9rem;">
        <p style="margin-bottom: 0.5rem;">
            <strong style="color: {BRAND_PRIMARY};">{BRAND_NAME}</strong> —
            Built with <span style="color: {BRAND_ACCENT};">♥</span> using dbt, DuckDB, BigQuery, and Streamlit
        </p>
        <p style="margin-bottom: 0.5rem; font-size: 0.85rem;">
            Data sources:
            <a href="https://www.rtd-denver.com/open-records" target="_blank" style="color: {BRAND_PRIMARY};">RTD GTFS</a> •
            <a href="https://www.denvergov.org/opendata/terms" target="_blank" style="color: {BRAND_PRIMARY};">Denver Open Data</a> •
            <a href="https://www.ncei.noaa.gov/" target="_blank" style="color: {BRAND_PRIMARY};">NOAA</a> •
            <a href="https://www.census.gov/" target="_blank" style="color: {BRAND_PRIMARY};">U.S. Census</a>
        </p>
        <p style="margin-bottom: 0; font-size: 0.85rem;">
            <a href="https://github.com/medsidd/whyline-denver" target="_blank" style="color: {BRAND_ACCENT};">View on GitHub</a> •
            <a href="https://medsidd.github.io/whyline-denver/" target="_blank" style="color: {BRAND_ACCENT};">dbt Docs</a>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
