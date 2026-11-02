"""RTD's reported on-time share beside WhyLine's measured one (WP10), run in DuckDB."""

from __future__ import annotations

import pandas as pd
from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)


def test_months_line_up_and_unmatched_sides_stay_null():
    con = connect()
    con.execute(
        "create table fct_rtd_reported_performance as select cast(m as date) as report_month, mode, "
        "service, metric, v as value_pct, 'u' as source_url from (values "
        "('2026-10-01', 'bus', 'all_bus', 'otp_month', 84.0), "
        "('2026-10-01', 'bus', 'all_bus', 'service_availability', 99.5), "
        "('2026-10-01', 'bus', 'local', 'otp_month', 83.0), "  # not compared
        "('2026-09-01', 'rail', 'commuter_rail_n', 'otp_month', 96.0)"
        ") as t(m, mode, service, metric, v)"
    )
    con.execute(
        "create table dim_route as select * from (values ('15', '3', true), ('117N', '2', true), "
        "('A', '2', true)) as t(route_id, route_type, is_latest_version)"
    )
    # October: four bus visits, three on time; one A Line visit late.
    con.execute(
        "create table fct_stop_visit as select cast(d as date) as service_date, r as route_id, delay_sec "
        "from (values ('2026-10-29', '15', 0), ('2026-10-29', '15', 120), ('2026-10-30', '15', -30), "
        "('2026-10-30', '15', 900), ('2026-10-30', 'A', 400), ('2026-10-30', '15', null)) as t(d, r, delay_sec)"
    )
    sql = render_model(
        "marts/reliability/mart_reported_vs_measured_by_month.sql",
        replacements=(
            (
                "date_trunc(v.service_date, month)",
                "cast(date_trunc('month', v.service_date) as date)",
            ),
        ),
    )
    out = con.execute(sql).df()
    out["report_month"] = out.report_month.astype(str)
    rows = out.set_index(["report_month", "service"])
    bus = rows.loc[("2026-10-01", "all_bus")]
    assert (bus.rtd_pct_on_time, bus.rtd_service_availability, bus.whyline_pct_on_time) == (
        0.84,
        0.995,
        0.75,
    )
    assert abs(bus.difference_pct_on_time - (0.75 - 0.84)) < 1e-9
    assert (bus.n_visits_measured, bus.n_days_measured) == (4, 2)
    assert pd.isna(
        rows.loc[("2026-10-01", "commuter_rail_abg"), "rtd_pct_on_time"]
    )  # measured only
    assert pd.isna(
        rows.loc[("2026-09-01", "commuter_rail_n"), "whyline_pct_on_time"]
    )  # reported only
    assert "local" not in set(out.service)
