"""Chart building utilities for data visualization."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

import altair as alt
import pandas as pd

try:
    import pydeck as pdk
except ImportError:
    pdk = None

# Import from app components (add app directory to path if needed)
if str(_Path(__file__).parent.parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
from components.branding import (
    BRAND_ACCENT,
    BRAND_ERROR,
    BRAND_PRIMARY,
    BRAND_SUCCESS,
    BRAND_WARNING,
    CHART_COLORS,
)


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

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW CHART TYPE 1: HEATMAP - Stop×Hour Reliability
    # ═══════════════════════════════════════════════════════════════════════════
    if {"event_hour_mst", "pct_on_time", "stop_id"} <= set(chart_df.columns):
        # Limit to top stops by average on-time percentage for readability
        top_stops = chart_df.groupby("stop_id")["pct_on_time"].mean().nlargest(20).index
        heatmap_df = chart_df[chart_df["stop_id"].isin(top_stops)].copy()

        # Ensure hour is treated as ordinal (0-23)
        heatmap_df["event_hour_mst"] = pd.to_numeric(heatmap_df["event_hour_mst"], errors="coerce")

        return (
            alt.Chart(heatmap_df)
            .mark_rect()
            .encode(
                x=alt.X(
                    "event_hour_mst:O",
                    title="Hour of Day (MST)",
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y("stop_id:N", sort="-color", title="Stop ID"),
                color=alt.Color(
                    "pct_on_time:Q",
                    scale=alt.Scale(scheme="blues", domain=[0, 100]),
                    title="On-Time %",
                    legend=alt.Legend(orient="right"),
                ),
                tooltip=[
                    alt.Tooltip("stop_id:N", title="Stop ID"),
                    alt.Tooltip("stop_name:N", title="Stop Name"),
                    alt.Tooltip("event_hour_mst:O", title="Hour"),
                    alt.Tooltip("pct_on_time:Q", title="On-Time %", format=".1f"),
                ],
            )
            .properties(title="Stop Reliability Heatmap (by Hour)", height=420, width=600)
            .configure_axis(labelColor="#c4b5a0", titleColor="#e8d5c4", gridColor="#433f4c")
            .configure_title(color=BRAND_ACCENT, fontSize=18, font="Space Grotesk", anchor="start")
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW CHART TYPE 2: WEATHER SMALL MULTIPLES - Faceted by Precipitation
    # ═══════════════════════════════════════════════════════════════════════════
    if {"precip_bin", "pct_on_time", "service_date_mst"} <= set(chart_df.columns):
        weather_df = chart_df.dropna(subset=["precip_bin", "pct_on_time", "service_date_mst"])

        # Limit to reasonable date range if too many points
        if len(weather_df) > 500:
            # Take most recent data
            weather_df = weather_df.nlargest(500, "service_date_mst")

        return (
            alt.Chart(weather_df)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X(
                    "service_date_mst:T",
                    title="Date",
                    axis=alt.Axis(labelAngle=-45, format="%m/%d"),
                ),
                y=alt.Y("pct_on_time:Q", title="On-Time %", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color(
                    "precip_bin:N",
                    title="Weather",
                    scale=alt.Scale(range=CHART_COLORS),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("service_date_mst:T", title="Date", format="%Y-%m-%d"),
                    alt.Tooltip("precip_bin:N", title="Weather"),
                    alt.Tooltip("pct_on_time:Q", title="On-Time %", format=".1f"),
                ],
            )
            .facet(column=alt.Column("precip_bin:N", title="Weather Condition"))
            .properties(title="Reliability by Weather Condition")
            .configure_axis(labelColor="#c4b5a0", titleColor="#e8d5c4", gridColor="#433f4c")
            .configure_title(color=BRAND_ACCENT, fontSize=18, font="Space Grotesk", anchor="start")
            .configure_header(labelColor="#e8d5c4", titleColor=BRAND_ACCENT)
        )

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

        tooltip_fields = [
            alt.Tooltip("service_date_mst:T", title="Date", format="%Y-%m-%d"),
            alt.Tooltip("pct_on_time:Q", title="On-Time %", format=".1f"),
        ]
        if "stop_name" in clean_df.columns:
            tooltip_fields.insert(0, alt.Tooltip("stop_name:N", title="Stop Name"))

        chart = (
            alt.Chart(clean_df)
            .mark_line(point=True, strokeWidth=3, size=80)
            .encode(
                x=alt.X("service_date_mst:T", title="Date"),
                y=alt.Y("pct_on_time:Q", title="On-Time %", scale=alt.Scale(domain=[0, 100])),
                tooltip=tooltip_fields
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


def _select_metric_column(map_df: pd.DataFrame) -> tuple[str | None, pd.Series | None]:
    """Pick a numeric column to use for radius/tooltip."""
    preferred_order = [
        "priority_score",
        "priority_rank",
        "crash_250m_cnt",
        "crash_100m_cnt",
        "vuln_score_0_100",
        "reliability_score_0_100",
        "pct_on_time",
    ]

    numeric_cols = [
        col
        for col in map_df.columns
        if pd.api.types.is_numeric_dtype(map_df[col]) and col not in {"lat", "lon"}
    ]

    for col in preferred_order:
        if col in numeric_cols:
            return col, map_df[col]

    for col in numeric_cols:
        if col not in {"stop_id"}:
            return col, map_df[col]

    return None, None


def build_map(df: pd.DataFrame, engine_module=None) -> object | None:
    """
    Build a pydeck hotspot map for priority stops.

    Args:
        df: DataFrame with stop_id and priority_score (or lon/lat columns)
        engine_module: Engine module to fetch stop geometry if needed

    Returns:
        pydeck.Deck object or None if pydeck not installed or insufficient data
    """
    if pdk is None:
        return None

    if df.empty or len(df) == 0:
        return None

    map_df = df.copy()

    def _sanitize_records(records: list[dict]) -> list[dict]:
        sanitized: list[dict] = []
        for record in records:
            clean: dict = {}
            for key, value in record.items():
                if hasattr(value, "item"):
                    value = value.item()
                elif isinstance(value, pd.Timestamp | pd.Timedelta):
                    value = value.isoformat()
                elif hasattr(value, "isoformat"):
                    try:
                        value = value.isoformat()
                    except Exception:
                        value = str(value)
                elif not isinstance(value, str | int | float | bool | type(None)):
                    value = str(value)
                clean[key] = value
            sanitized.append(clean)
        return sanitized

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW MAP TYPE: HOTSPOT MAP - Priority Stops
    # ═══════════════════════════════════════════════════════════════════════════
    if "stop_id" in map_df.columns:
        # Check if lat/lon already present
        if not (
            {"lat", "lon"} <= set(map_df.columns) or {"stop_lat", "stop_lon"} <= set(map_df.columns)
        ):
            # Need to join with stg_gtfs_stops to get geometry
            if engine_module is not None:
                try:
                    # Load stop geometry from staging layer
                    from whylinedenver.config import settings

                    if hasattr(engine_module, "execute"):
                        # Determine table name based on engine
                        if "bigquery" in str(type(engine_module)).lower():
                            stops_table = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_STG}.stg_gtfs_stops`"
                        else:
                            stops_table = "stg_gtfs_stops"

                        _, stops_df = engine_module.execute(
                            f"SELECT stop_id, stop_name, stop_lat, stop_lon FROM {stops_table}"
                        )

                        # Join with map data
                        map_df = map_df.merge(stops_df, on="stop_id", how="inner")
                except Exception:
                    # If join fails, can't render map
                    return None
            else:
                # No engine provided, can't fetch geometry
                return None

        # Standardize column names
        if "stop_lat" in map_df.columns:
            map_df = map_df.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})

        if "stop_name" not in map_df.columns:
            map_df["stop_name"] = map_df.get("stop_id", "")
        else:
            map_df["stop_name"] = map_df["stop_name"].fillna(map_df.get("stop_id", ""))

        # Filter out invalid coordinates
        map_df = map_df.dropna(subset=["lat", "lon"])
        map_df = map_df[(map_df["lat"] != 0) & (map_df["lon"] != 0)]

        if len(map_df) == 0:
            return None

        metric_col, metric_series = _select_metric_column(map_df)
        metric_label = None
        if metric_col and metric_series is not None:
            metric_values = metric_series.fillna(0).abs()
            max_val = metric_values.max()
            if max_val > 0:
                map_df["radius"] = (metric_values / max_val) * 200 + 50
            else:
                map_df["radius"] = 100
            map_df["metric_value_display"] = metric_series.round(2).fillna("–")
            metric_label = metric_col.replace("_", " ").title()
        else:
            map_df["radius"] = 120
            metric_col = None
            metric_label = None
            map_df["metric_value_display"] = "–"

        # Create scatterplot layer
        map_df["radius"] = map_df["radius"].astype(float)
        records = _sanitize_records(map_df.to_dict(orient="records"))

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=records,
            get_position="[lon, lat]",
            get_radius="radius",
            get_fill_color=f"[{int(BRAND_ERROR[1:3], 16)}, {int(BRAND_ERROR[3:5], 16)}, {int(BRAND_ERROR[5:7], 16)}, 160]",
            pickable=True,
            auto_highlight=True,
        )

        # Set initial view state (Denver coordinates)
        view_state = pdk.ViewState(
            latitude=map_df["lat"].mean() if len(map_df) > 0 else 39.7392,
            longitude=map_df["lon"].mean() if len(map_df) > 0 else -104.9903,
            zoom=11,
            pitch=0,
        )

        # Create deck with custom tooltip
        tooltip_html = "<b>Stop:</b> {stop_name} ({stop_id})"
        if metric_label:
            tooltip_html += f"<br/><b>{metric_label}:</b> {{metric_value_display}}"

        return pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="mapbox://styles/mapbox/dark-v10",
            tooltip={
                "html": tooltip_html,
                "style": {
                    "backgroundColor": "#322e38",
                    "color": "#e8d5c4",
                    "fontSize": "14px",
                    "fontFamily": "Inter, sans-serif",
                },
            },
        )

    return None
