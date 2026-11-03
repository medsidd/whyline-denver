"""Job access mart (WP12): thresholds pivoted per tract and window, in DuckDB."""

from __future__ import annotations

import pandas as pd
from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)


def test_thresholds_pivot_and_region_share():
    con = connect()
    con.execute(
        "create table fct_job_access as select g as geoid, w as departure_window, date '2026-11-03' as departure_date, "
        "m as minutes_threshold, j as jobs_reachable, 1000 as total_jobs_region, 2023 as lodes_year, 'x' as gtfs_md5 "
        "from (values ('08031002901', 'weekday_am_peak', 30, 100), ('08031002901', 'weekday_am_peak', 45, 250), "
        "('08031002901', 'weekday_am_peak', 60, 600), ('08005005600', 'weekday_am_peak', 45, 10)) as t(g, w, m, j)"
    )
    con.execute(
        "create table stg_arcgis_reference as select 'enviroscreen_tract' as layer, "
        '\'{"GEOID": "08031002901", "ES_S_": 61.5}\' as properties_json'
    )
    sql = render_model(
        "marts/access/mart_job_access_by_tract.sql",
        replacements=(
            ("safe_cast(", "try_cast("),
            ("as float64)", "as double)"),
            ("json_value(", "json_extract_string("),
        ),
    )
    out = con.execute(sql).df().set_index("geoid")
    denver = out.loc["08031002901"]
    assert (denver.jobs_within_30min, denver.jobs_within_45min, denver.jobs_within_60min) == (
        100,
        250,
        600,
    )
    assert (
        denver.pct_region_jobs_45min == 0.25
        and denver.is_denver
        and denver.enviroscreen_pctl == 61.5
    )
    aurora = out.loc["08005005600"]
    assert (
        not aurora.is_denver
        and pd.isna(aurora.jobs_within_30min)
        and pd.isna(aurora.enviroscreen_pctl)
    )
