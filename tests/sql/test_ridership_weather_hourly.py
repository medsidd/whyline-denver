"""NTD ridership and hourly-weather reliability (WP11, WP13), run in DuckDB."""

from __future__ import annotations

import pandas as pd
from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)


def test_ridership_by_mode_compares_the_same_month_a_year_earlier():
    con = connect()
    rows = [
        # Bus is reported directly operated and purchased; they add up per month.
        *[(f"2025-{m:02d}-01", "MB", "DO", "Bus", 1000 + m, 100) for m in range(1, 13)],
        *[(f"2025-{m:02d}-01", "MB", "PT", "Bus", 500, 50) for m in range(1, 13)],
        ("2026-01-01", "MB", "DO", "Bus", 1201, 100),
        ("2026-01-01", "MB", "PT", "Bus", 500, 50),
        # Vanpool skips months: January 2026 has no January 2025 to compare with.
        ("2025-03-01", "VP", "PT", "Bus", 90, 30),
        ("2026-01-01", "VP", "PT", "Bus", 80, 40),
    ]
    con.execute(
        "create table fct_ntd_service_month as select cast(m as date) as month, mode, tos, mode_group, "
        "upt, 0 as vrm, vrh, 1 as voms from (values "
        + ", ".join(f"('{m}', '{mo}', '{t}', '{g}', {u}, {h})" for m, mo, t, g, u, h in rows)
        + ") as t(m, mode, tos, mode_group, upt, vrh)"
    )
    out = con.execute(render_model("marts/ridership/mart_ridership_by_mode_month.sql")).df()
    jan = out[out.month.astype(str) == "2026-01-01"].set_index("mode")
    assert jan.loc["MB", "boardings"] == 1701 and jan.loc["MB", "boardings_year_earlier"] == 1501
    assert jan.loc["MB", "boardings_yoy_change"] == round(1701 / 1501 - 1, 4)
    assert jan.loc["MB", "boardings_per_revenue_hour"] == round(1701 / 150, 2)
    assert jan.loc["MB", "mode_name"] == "Bus" and jan.loc["VP", "mode_name"] == "Vanpool"
    assert pd.isna(jan.loc["VP", "boardings_year_earlier"])


def test_latest_extract_wins_and_visits_take_their_hours_weather():
    con = connect()
    con.execute(
        "create table raw_weather_hourly as select * from (values "
        "(timestamp '2026-11-01 15:00:00', 'USW00003017', 0.0, 0.0, 5.0, 10.0, 'open_meteo_forecast', date '2026-11-01', timestamp '2026-11-01 08:00:00'),"
        "(timestamp '2026-11-01 15:00:00', 'USW00003017', 2.0, 5.0, -1.0, 10.0, 'open_meteo_archive', date '2026-11-08', timestamp '2026-11-08 08:00:00'),"
        "(timestamp '2026-11-01 16:00:00', 'USW00003017', 0.0, 0.0, 6.0, 10.0, 'open_meteo_forecast', date '2026-11-01', timestamp '2026-11-01 08:00:00')"
        ") as t(ts_utc, station, precip_mm, snowfall_mm, temp_c, wind_kmh, source, _extract_date, _ingested_at)"
    )
    stg = con.execute(render_model("staging/stg_weather_hourly.sql")).df().set_index("ts_utc")
    assert len(stg) == 2
    assert (
        stg.loc[pd.Timestamp("2026-11-01 15:00:00"), "source"] == "open_meteo_archive"
    )  # later extract

    con.execute(
        f"create table stg_weather_hourly as {render_model('staging/stg_weather_hourly.sql')}"
    )
    con.execute(f"create table fct_weather_hourly as {render_model('core/fct_weather_hourly.sql')}")
    # Route 15: two visits in the snowy 15:00 hour (one late), two in the dry 16:00 hour.
    con.execute(
        "create table fct_stop_visit as select current_date - 1 as service_date, '15' as route_id, "
        "cast(a as timestamptz) as arrival_ts_utc, d as delay_sec from (values "
        "('2026-11-01 15:10:00', 60), ('2026-11-01 15:40:00', 600), "
        "('2026-11-01 16:05:00', 0), ('2026-11-01 16:30:00', 30), ('2026-11-01 16:45:00', null)) as t(a, d)"
    )
    sql = render_model(
        "marts/reliability/mart_weather_impacts_hourly.sql",
        variables={"weather_station": "USW00003017", "weather_hourly_window_days": 10000},
        replacements=(
            ("timestamp_trunc(v.arrival_ts_utc, hour)", "date_trunc('hour', v.arrival_ts_utc)"),
            ("approx_quantiles(delay_sec, 10)[offset(9)]", "quantile_disc(delay_sec, 0.9)"),
        ),
    )
    out = con.execute(sql).df().set_index(["factor", "level"])
    assert out.loc[("snowfall", "snowing"), "n_visits"] == 2
    assert out.loc[("snowfall", "snowing"), "pct_on_time"] == 0.5
    assert out.loc[("snowfall", "not_snowing"), "pct_on_time"] == 1.0
    assert out.loc[("snowfall", "snowing"), "delta_pct_on_time"] == -0.5
    assert out.loc[("precipitation", "moderate"), "n_visits"] == 2  # 2 mm in the hour
    assert out.loc[("temperature", "-10_to_0"), "delta_pct_on_time"] == -0.5
