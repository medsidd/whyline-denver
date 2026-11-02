"""Wait time (WP4): observed headways, excess wait, bunching and gaps, run in DuckDB."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

QUANTILES = (("approx_quantiles(delay_sec, 10)[offset(9)]", "quantile_disc(delay_sec, 0.9)"),)


def _inputs(con):
    day = "cast(current_date - 1 as date)"
    ts = lambda t: f"cast(current_date - 1 as timestamptz) + interval '{t}'"  # noqa: E731
    # (trip, method, arrival UTC, scheduled headway, delay, had_vehicle); scheduled every 10 min.
    visits = [
        ("T1", "origin_departure", "16:00:00", None, 0, True),
        ("T2", "shape_crossing", "16:10:00", 600, 0, True),
        ("T3", "shape_crossing_gap", "16:12:00", 600, -480, True),  # bunched: 2 min behind T2
        ("T4", "last_prediction", "16:30:00", 600, 0, False),  # ghost: predictions only
        ("T5", "shape_crossing", "16:41:00", 600, 60, True),  # gap: 29 min after T3
        ("T6", "last_prediction", "16:50:00", 600, 0, True),  # ran, but not seen crossing
        ("T7", "skipped", None, 600, None, True),
    ]
    con.execute(
        "create table fct_stop_visit as "
        + " union all ".join(
            f"select {day} as service_date, 'S1' as stop_id, '15' as route_id, 0 as direction_id, "
            f"'{t}' as trip_id, 3 as stop_sequence, '{m}' as arrival_method, "
            f"{ts(a) if a else 'null'} as arrival_ts_utc, "
            f"cast({'null' if s is None else s} as int) as scheduled_headway_sec, "
            f"cast({'null' if d is None else d} as int) as delay_sec"
            for t, m, a, s, d, _ in visits
        )
    )
    con.execute(
        "create table fct_trip_status as "
        + " union all ".join(
            f"select {day} as service_date, '{t}' as trip_id, {v} as had_vehicle"
            for t, *_, v in visits
        )
    )
    con.execute(
        "create table dim_stop as select 'S1' as stop_id, 'First' as stop_name, 39.7 as lat, "
        "-105.0 as lon, true as is_current"
    )


def test_headways_and_excess_wait():
    con = connect()
    _inputs(con)
    sql = render_model("core/fct_stop_headway.sql", incremental=True)
    rows = con.execute(sql).df().set_index("trip_id")
    assert set(rows.index) == {"T1", "T2", "T3", "T5", "T6"}  # no ghost, no skipped stop
    assert rows.observed_headway_sec.dropna().astype(int).to_dict() == {
        "T2": 600,
        "T3": 120,
        "T5": 1740,
        "T6": 540,
    }

    con.execute(f"create table fct_stop_headway as {sql}")
    # Headways 600, 120, 1740, 540 against 600 scheduled: 3,693,600 / 6,000 and 300 s.
    for model, wait_col in (
        ("marts/realtime/mart_wait_by_stop_period.sql", "n_headways"),
        ("marts/realtime/mart_wait_by_route_day.sql", "n_frequent_headways"),
    ):
        out = con.execute(render_model(model, replacements=QUANTILES)).df()
        assert len(out) == 1, model
        r = out.iloc[0]
        assert r[wait_col] == 4
        assert abs(r.expected_wait_sec - 615.6) < 1e-6 and r.scheduled_wait_sec == 300
        assert abs(r.excess_wait_sec - 315.6) < 1e-6
        assert (r.pct_bunched, r.pct_gap) == (0.25, 0.25)
        assert r.pct_on_time == 0.8  # T3 came 8 minutes early
    stop = (
        con.execute(
            render_model("marts/realtime/mart_wait_by_stop_period.sql", replacements=QUANTILES)
        )
        .df()
        .iloc[0]
    )
    assert stop.service_class == "frequent" and stop.stop_name == "First"
    assert stop.period == "midday"  # 16:00 UTC is 9:00 or 10:00 in Denver
