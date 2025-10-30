# ruff: noqa: E402,I001
"""Results viewer component (Step 3) - Display results, charts, and download."""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime
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
from utils.data_loaders import load_stop_lookup
from utils.formatting import format_timestamp, human_readable_bytes

MART_OPTIONS: list[tuple[str, str]] = [
    ("mart_reliability_by_route_day", "Reliability by route & day"),
    ("mart_reliability_by_stop_hour", "Reliability by stop & hour"),
    ("mart_crash_proximity_by_stop", "Crash proximity by stop"),
    ("mart_access_score_by_stop", "Access score by stop"),
    ("mart_vulnerability_by_stop", "Vulnerability by stop"),
    ("mart_priority_hotspots", "Priority hotspots"),
    ("mart_weather_impacts", "Weather impacts"),
]
MART_LABELS = {value: label for value, label in MART_OPTIONS}

FULL_MART_DOWNLOAD_STATE = "full_mart_download_state"
FULL_MART_DOWNLOAD_ERROR = "full_mart_download_error"

_warehouse_env = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
WAREHOUSE_PATH = Path(_warehouse_env).expanduser()
if not WAREHOUSE_PATH.is_absolute():
    WAREHOUSE_PATH = (ROOT / WAREHOUSE_PATH).resolve()


def _date_columns_for_mart(mart: str, models: dict[str, ModelInfo]) -> list[str]:
    info = models.get(mart)
    if not info:
        return []
    candidates: list[str] = []
    for name, column in info.columns.items():
        col_type = (column.type or "").upper()
        if "DATE" in col_type or "DATE" in name.upper():
            candidates.append(name)
    # Deduplicate while preserving order preference (service_date_mst first if present)
    seen: set[str] = set()
    ordered: list[str] = []
    preferred = ["service_date_mst", "as_of_date"]
    for pref in preferred:
        if pref in candidates:
            ordered.append(pref)
            seen.add(pref)
    for name in candidates:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


@st.cache_data(ttl=180, show_spinner=False)
def _execute_query_cached(
    engine: str, sql: str, _models: dict[str, ModelInfo]
) -> pd.DataFrame | None:
    """
    Execute a query and cache the result for 3 minutes.

    This cached function retrieves results from query_cache when available,
    preventing repeated execution of the same query.

    Args:
        engine: Engine name (duckdb or bigquery)
        sql: Sanitized and adapted SQL query
        _models: Models dict (prefixed with _ to exclude from cache key)

    Returns:
        DataFrame with query results or None on error
    """
    engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine

    # Check query_cache first (very fast)
    cached = query_cache.get(engine, sql)
    if cached:
        _, df = cached
        return df

    # Execute if not in cache (shouldn't happen often)
    try:
        _, df = engine_module.execute(sql)
        return df
    except Exception:  # noqa: BLE001
        return None


def _load_date_bounds(
    engine: str,
    mart: str,
    column: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> tuple[date | None, date | None, str | None]:
    """Fetch the available date range for a mart column with guardrail enforcement."""
    engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
    sql = f"SELECT MIN({column}) AS min_value, MAX({column}) AS max_value FROM {mart}"
    try:
        sanitized = sanitize_sql(sql, guardrail_config)
        adapted = adapt_sql_for_engine(sanitized, engine, models)
        _, df = engine_module.execute(adapted)
    except SqlValidationError as exc:
        return None, None, str(exc)
    except Exception as exc:  # noqa: BLE001 - surface to UI as warning
        return None, None, str(exc)

    if df.empty:
        return None, None, "No data available for selected mart"

    min_raw = df.loc[0, "min_value"]
    max_raw = df.loc[0, "max_value"]
    try:
        min_date = pd.to_datetime(min_raw).date() if pd.notna(min_raw) else None
        max_date = pd.to_datetime(max_raw).date() if pd.notna(max_raw) else None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Failed to parse date bounds: {exc}"
    return min_date, max_date, None


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
    generated_sql = st.session_state.get("generated_sql")
    query_params = st.session_state.get("query_params")

    if not generated_sql and query_params is None:
        st.markdown("### Downloads")
        st.caption("Retrieve full marts or the DuckDB warehouse without generating SQL first.")
        _render_downloads_section(engine, models, guardrail_config)
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
        if query_params is not None:
            # Compute row count from cached execution
            results_df = _execute_query_cached(query_params["engine"], query_params["sql"], models)
            if results_df is not None:
                st.success(f"✓ Query executed successfully ({len(results_df)} rows)")

    if run_clicked:
        sql_to_run = st.session_state.get("edited_sql", st.session_state["generated_sql"])
        try:
            sanitized_sql = sanitize_sql(sql_to_run, guardrail_config)
            sanitized_sql = adapt_sql_for_engine(sanitized_sql, engine, models)
            st.session_state["sanitized_sql"] = sanitized_sql
        except SqlValidationError as exc:
            st.session_state["run_error"] = str(exc)
            st.session_state["query_params"] = None
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
                    # Store only parameters, not the DataFrame
                    st.session_state["query_params"] = {
                        "engine": engine,
                        "sql": sanitized_sql,
                        "question": question,
                    }
                    st.session_state["results_stats"] = stats
                    st.session_state["run_error"] = None
                except Exception as exc:
                    st.session_state["run_error"] = str(exc)
                    st.session_state["query_params"] = None
                    st.session_state["results_stats"] = None

    if st.session_state.get("run_error"):
        st.error(f"❌ Query failed: {st.session_state['run_error']}")

    query_params = st.session_state.get("query_params")
    results_stats = st.session_state.get("results_stats")

    if query_params is not None:
        # Recompute from cached execution - this is very fast due to query_cache
        results_df = _execute_query_cached(query_params["engine"], query_params["sql"], models)

        if results_df is None:
            st.error("❌ Failed to retrieve cached results")
            return

        display_df = results_df.copy()

        if "stop_id" in display_df.columns:
            stop_lookup = load_stop_lookup(engine)
            if not stop_lookup.empty and "error" not in stop_lookup.columns:
                stop_lookup = stop_lookup.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})
                stop_lookup["stop_id"] = stop_lookup["stop_id"].astype(str)
                display_df["stop_id"] = display_df["stop_id"].astype(str)
                display_df = display_df.merge(
                    stop_lookup,
                    on="stop_id",
                    how="left",
                    suffixes=("", "_ref"),
                )
                for base in ("stop_name", "lat", "lon"):
                    ref_col = f"{base}_ref"
                    if ref_col in display_df.columns:
                        if base in display_df.columns:
                            display_df[base] = display_df[base].where(
                                display_df[base].notna(), display_df[ref_col]
                            )
                        else:
                            display_df[base] = display_df[ref_col]
                        display_df = display_df.drop(columns=[ref_col])
            else:
                display_df["stop_id"] = display_df["stop_id"].astype(str)

        # Execution stats in expander
        if results_stats:
            with st.expander("Execution Statistics", expanded=False):
                st.json(results_stats)

        # Downsample for display if too large (memory optimization)
        max_display_rows = 10_000
        display_sample = display_df
        if len(display_df) > max_display_rows:
            st.warning(
                f"⚠️ Large result set ({len(display_df):,} rows). "
                f"Displaying first {max_display_rows:,} rows. "
                "Download full CSV below."
            )
            display_sample = display_df.head(max_display_rows)

        # Results table
        st.dataframe(display_sample, use_container_width=True)

        # Visualization - use downsampled data for charts
        chart = build_chart(display_sample)
        if chart:
            st.altair_chart(chart, use_container_width=True)

        # Map visualization - limit to reasonable number of points
        engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
        map_sample = display_df.head(1000) if len(display_df) > 1000 else display_df
        hotspot_map = build_map(map_sample, engine_module)
        if hotspot_map:
            if len(display_df) > 1000:
                st.caption(f"ℹ️ Map showing top 1,000 of {len(display_df):,} points")
            st.pydeck_chart(hotspot_map)

        # Download button
        csv_data = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv_data,
            file_name="whylinedenver_results.csv",
            mime="text/csv",
            use_container_width=True,
        )
    elif not st.session_state.get("run_error"):
        st.info("👆 Run the query to see results")

    _render_downloads_section(engine, models, guardrail_config)


def _render_downloads_section(
    engine: str,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> None:
    """Render the downloads expander with mart exports and DuckDB snapshot."""
    with st.expander("Downloads", expanded=False):
        available_marts = [mart for mart, _ in MART_OPTIONS if mart in models]

        st.markdown("#### Full mart CSV exports")
        if available_marts:
            mart = st.selectbox(
                "Choose mart",
                options=available_marts,
                format_func=_mart_label,
                key="full_mart_download_mart",
            )
            limit_rows = st.number_input(
                "Row cap (safety)",
                min_value=1_000,
                max_value=2_000_000,
                value=200_000,
                step=1_000,
                key="full_mart_download_limit",
            )
            date_columns = _date_columns_for_mart(mart, models)
            date_column = date_columns[0] if date_columns else None
            filter_enabled = False
            date_start: date | None = None
            date_end: date | None = None

            if date_column:
                if len(date_columns) > 1:
                    others = ", ".join(date_columns[1:])
                    st.caption(
                        f"ℹ️ Using `{date_column}` for date filtering. Additional date-like columns detected: {others}."
                    )
                filter_key = f"full_mart_download_apply_dates_{mart}"
                if filter_key not in st.session_state:
                    st.session_state[filter_key] = False
                filter_enabled = st.checkbox(
                    f"Filter by {date_column}",
                    key=filter_key,
                    help=f"Apply an optional date window against `{date_column}` before exporting.",
                )
                if filter_enabled:
                    min_date, max_date, date_error = _load_date_bounds(
                        engine, mart, date_column, models, guardrail_config
                    )
                    if date_error:
                        st.warning(f"⚠️ Unable to load date range: {date_error}")
                        st.info("Please uncheck the filter to proceed without date filtering.")
                        filter_enabled = False
                    elif min_date and max_date:
                        start_key = f"full_mart_download_start_{mart}_{date_column}"
                        end_key = f"full_mart_download_end_{mart}_{date_column}"
                        default_start = st.session_state.get(start_key) or min_date
                        default_end = st.session_state.get(end_key) or max_date
                        col_start, col_end = st.columns(2)
                        date_start = col_start.date_input(
                            "Start date",
                            value=default_start,
                            min_value=min_date,
                            max_value=max_date,
                            key=start_key,
                        )
                        date_end = col_end.date_input(
                            "End date",
                            value=default_end,
                            min_value=min_date,
                            max_value=max_date,
                            key=end_key,
                        )
                    else:
                        st.warning("Date bounds unavailable; export will include all rows.")
                        st.info("Please uncheck the filter to proceed without date filtering.")
                        filter_enabled = False
            else:
                st.caption(
                    "ℹ️ No date-like columns detected for this mart; exports will include all rows up to the safety cap."
                )

            prepare_clicked = st.button(
                "Prepare CSV export",
                use_container_width=True,
                key="full_mart_download_prepare",
            )

            if prepare_clicked:
                st.session_state.pop(FULL_MART_DOWNLOAD_STATE, None)
                st.session_state.pop(FULL_MART_DOWNLOAD_ERROR, None)
                if filter_enabled and date_start and date_end and date_start > date_end:
                    st.session_state[FULL_MART_DOWNLOAD_ERROR] = (
                        "Start date must be on or before the end date."
                    )
                else:
                    date_filter = (
                        (date_column, date_start, date_end)
                        if filter_enabled and date_column and date_start and date_end
                        else None
                    )
                    with st.spinner("Preparing mart export (guard-railed SQL)…"):
                        try:
                            payload = _prepare_mart_download(
                                engine=engine,
                                mart=mart,
                                limit_rows=int(limit_rows),
                                date_filter=date_filter,
                                models=models,
                                guardrail_config=guardrail_config,
                            )
                        except SqlValidationError as exc:
                            st.session_state[FULL_MART_DOWNLOAD_ERROR] = str(exc)
                        except Exception as exc:  # noqa: BLE001 - surface to user
                            st.session_state[FULL_MART_DOWNLOAD_ERROR] = str(exc)
                        else:
                            st.session_state[FULL_MART_DOWNLOAD_STATE] = payload
                            st.session_state[FULL_MART_DOWNLOAD_ERROR] = None
        else:
            st.info("No allow-listed marts are available for export in this environment.")

        payload = st.session_state.get(FULL_MART_DOWNLOAD_STATE)
        if payload and payload.get("engine") != engine:
            payload = None
        error = st.session_state.get(FULL_MART_DOWNLOAD_ERROR)

        if error:
            st.error(f"❌ {error}")
        elif payload:
            mart_label = _mart_label(payload["mart"])
            success_message = (
                f"Prepared {payload['rows']:,} rows from {mart_label} on {payload['engine']}."
            )
            if payload.get("date_column") and payload.get("date_start") and payload.get("date_end"):
                success_message += (
                    f" Filtered by {payload['date_column']} between {payload['date_start']} and"
                    f" {payload['date_end']}."
                )
            st.success(success_message)
            st.download_button(
                label="⬇️ Download prepared CSV",
                data=payload["csv_bytes"],
                file_name=payload["file_name"],
                mime="text/csv",
                use_container_width=True,
                key="full_mart_download_button",
            )
            summary = f"Limit {payload['limit']:,}"
            if payload.get("date_start") and payload.get("date_end"):
                column = payload.get("date_column") or "date"
                summary += f" • {column}: {payload['date_start']} → {payload['date_end']}"
            summary += f" • Prepared {payload['prepared_at']} UTC"
            st.caption(summary)
            st.code(payload["sanitized_sql"], language="sql")

        st.markdown("---")
        st.markdown("#### DuckDB warehouse snapshot")
        if WAREHOUSE_PATH.exists():
            stats = WAREHOUSE_PATH.stat()
            last_modified_iso = (
                datetime.utcfromtimestamp(stats.st_mtime).replace(microsecond=0).isoformat() + "Z"
            )
            st.download_button(
                label="🦆📦 Download DuckDB warehouse",
                data=_load_duckdb_bytes(str(WAREHOUSE_PATH), stats.st_mtime),
                file_name=WAREHOUSE_PATH.name,
                mime="application/octet-stream",
                use_container_width=True,
                key="warehouse_duckdb_download",
            )
            st.caption(
                f"{human_readable_bytes(stats.st_size)} • Last sync {format_timestamp(last_modified_iso)}"
            )
        else:
            st.warning(
                f"DuckDB warehouse not found at `{WAREHOUSE_PATH}`. "
                "Run `make sync-duckdb` to materialize the local database."
            )


def _mart_label(mart: str) -> str:
    return MART_LABELS.get(mart, mart)


def _build_download_filename(
    mart: str,
    engine: str,
    date_filter: tuple[str, date, date] | None,
) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    suffix = ""
    if date_filter:
        column, start, end = date_filter
        suffix = f"_{column}_{start}_{end}"
    return f"{mart}_{engine}{suffix}_{timestamp}.csv"


def _prepare_mart_download(
    *,
    engine: str,
    mart: str,
    limit_rows: int,
    date_filter: tuple[str, date, date] | None,
    models: dict[str, ModelInfo],
    guardrail_config: GuardrailConfig,
) -> dict[str, object]:
    sql = f"SELECT * FROM {mart}"
    conditions: list[str] = []
    if date_filter:
        column, start, end = date_filter
        conditions.append(
            f"{column} BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'"
        )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += f" LIMIT {int(limit_rows)}"

    sanitized_sql = sanitize_sql(sql, guardrail_config)
    adapted_sql = adapt_sql_for_engine(sanitized_sql, engine, models)

    engine_module = duckdb_engine if engine == "duckdb" else bigquery_engine
    cached = query_cache.get(engine, sanitized_sql)
    cache_hit = False
    latency_ms = 0.0
    if cached:
        stats, df = cached
        cache_hit = True
    else:
        start_time = time.monotonic()
        stats, df = engine_module.execute(adapted_sql)
        latency_ms = (time.monotonic() - start_time) * 1000
        query_cache.set(engine, sanitized_sql, (stats, df))

    query_label = f"[download] {mart}"
    if date_filter:
        query_label = f"{query_label} [{date_filter[0]}]"

    log_query(
        engine=engine,
        rows=len(df),
        latency_ms=latency_ms,
        models=[mart],
        sql=sanitized_sql,
        question=query_label,
        cache_hit=cache_hit,
        bq_est_bytes=stats.get("bq_est_bytes") if isinstance(stats, dict) else None,
    )

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    if date_filter:
        column, start, end = date_filter
        date_start_str = start.isoformat()
        date_end_str = end.isoformat()
        date_column = column
    else:
        date_start_str = None
        date_end_str = None
        date_column = None
    return {
        "mart": mart,
        "engine": engine,
        "limit": int(limit_rows),
        "rows": len(df),
        "date_column": date_column,
        "date_start": date_start_str,
        "date_end": date_end_str,
        "csv_bytes": csv_bytes,
        "sanitized_sql": sanitized_sql,
        "file_name": _build_download_filename(mart, engine, date_filter),
        "prepared_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    }


@st.cache_data(show_spinner=False)
def _load_duckdb_bytes(path_str: str, mtime: float) -> bytes:
    """Cache the warehouse bytes keyed by modification time to avoid repeated reads."""
    return Path(path_str).read_bytes()
