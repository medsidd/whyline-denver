"""Bus-lane speed comparison (lane vs the same routes elsewhere), run in DuckDB."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

DUCKDB = (
    (
        "date_trunc(t.service_date, week(monday))",
        "cast(date_trunc('week', t.service_date) as date)",
    ),
    ("approx_quantiles(g.speed_kmh, 100)[offset(50)]", "quantile_disc(g.speed_kmh, 0.5)"),
    ("approx_quantiles(g.delay_ratio, 100)[offset(50)]", "quantile_disc(g.delay_ratio, 0.5)"),
)


def _inputs(con):
    con.execute(
        "create table bridge_segment_transit_lane as select * from (values "
        "('S1', 'S2', 'Broadway', 'BAT 24-hour', 2017)) as t(from_stop_id, to_stop_id, corridor, lane_type, year_built)"
    )
    # Route 0 uses the lane (S1-S2) and runs elsewhere (S2-S3); route 9 never touches the lane.
    con.execute(
        "create table fct_segment_traversal as select date '2026-11-02' as service_date, * from (values "
        "('0', 'S1', 'S2', 12, 15.0, 90, 100), ('0', 'S1', 'S2', 12, 17.0, 110, 100), "
        "('0', 'S2', 'S3', 12, 25.0, 80, 100), ('9', 'S7', 'S8', 12, 40.0, 50, 100)"
        ") as t(route_id, from_stop_id, to_stop_id, depart_hour_mst, speed_kmh, travel_sec, scheduled_travel_sec)"
    )


def test_lane_segments_beside_the_same_routes_elsewhere():
    con = connect()
    _inputs(con)
    out = (
        con.execute(
            render_model(
                "marts/reliability/mart_transit_lane_speed_by_week.sql", replacements=DUCKDB
            )
        )
        .df()
        .set_index("segment_group")
    )
    assert set(out.index) == {"lane", "same_routes_no_lane"}  # route 9 isn't a comparison
    assert (out.loc["lane", "n_traversals"], out.loc["lane", "p50_speed_kmh"]) == (2, 15.0)
    assert (
        out.loc["same_routes_no_lane", "p50_speed_kmh"],
        out.loc["same_routes_no_lane", "p50_delay_ratio"],
    ) == (25.0, 0.8)
    assert out.loc["lane", "first_year_built"] == 2017 and out.weeks_since_opening.isna().all()


def test_weeks_since_opening_for_a_dated_lane():
    con = connect()
    _inputs(con)
    sql = render_model(
        "marts/reliability/mart_transit_lane_speed_by_week.sql",
        variables={"lane_openings": {"Broadway": "2026-10-19"}},
        replacements=DUCKDB + (("week(monday))", "'week')"),),
    )
    sql = sql.replace(
        "date_diff(g.week_start, date '2026-10-19', 'week')",
        "date_diff('week', date '2026-10-19', g.week_start)",
    )
    out = con.execute(sql).df()
    assert set(out.weeks_since_opening) == {2}  # week of 2026-11-02 vs week of 2026-10-19
