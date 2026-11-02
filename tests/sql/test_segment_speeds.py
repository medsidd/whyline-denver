"""Segment speeds and trip run times (WP5), run in DuckDB."""

from __future__ import annotations

import re

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

QUANTILE = re.compile(r"approx_quantiles\((\w+), 100\)\[offset\((\d+)\)\]")


def _duckdb(sql: str) -> str:
    return QUANTILE.sub(lambda m: f"quantile_disc({m[1]}, {int(m[2]) / 100})", sql)


def _ts(clock):
    return f"cast(current_date - 1 as timestamptz) + interval '{clock}'" if clock else "null"


def _inputs(con):
    # (seq, role, method, within_30s, dist_m, scheduled) shared by every trip.
    stops = [
        (1, "first", "origin_departure", 0, "10:00:00"),
        (2, "middle", "shape_crossing", 1000, "10:02:00"),
        (3, "middle", "shape_crossing_gap", 2000, "10:04:00"),  # not timed to 30 s
        (4, "middle", "shape_crossing", 3000, "10:06:00"),
        (5, "last", "shape_crossing", 4500, "10:10:00"),
    ]
    # Per trip: arrival at each stop and stop 2's departure window.
    trips = {
        "T1": (
            ["10:00:00", "10:02:00", "10:05:00", "10:07:00", "10:10:00"],
            ("10:02:20", "10:02:40"),
        ),
        "T2": (["10:20:00", "10:23:00", "10:26:00", "10:28:00", "10:32:00"], (None, None)),
    }
    rows = []
    for trip, (arrivals, (dep_from, dep_to)) in trips.items():
        offset = "00:20:00" if trip == "T2" else "00:00:00"
        for (seq, role, method, dist, sched), arrival in zip(stops, arrivals, strict=True):
            within = method != "shape_crossing_gap"
            dep = (dep_from, dep_to) if seq == 2 else (None, None)
            rows.append(
                f"select cast(current_date - 1 as date) as service_date, '{trip}' as trip_id, '15' as route_id, "
                f"0 as direction_id, {seq} as stop_sequence, 'S{seq}' as stop_id, '{role}' as stop_role, "
                f"'{method}' as arrival_method, {within} as within_30s, {dist}.0 as stop_dist_m, "
                f"{_ts(arrival)} as arrival_ts_utc, {_ts(dep[0])} as departure_earliest_ts, "
                f"{_ts(dep[1])} as departure_latest_ts, "
                f"{_ts(sched)} + interval '{offset}' as scheduled_arrival_ts, "
                f"{_ts(sched)} + interval '{offset}' as scheduled_departure_ts"
            )
    con.execute("create table fct_stop_visit as " + " union all ".join(rows))
    con.execute(
        "create table dim_stop as select 'S' || i as stop_id, 'Stop ' || i as stop_name, "
        "39.7 + i / 100 as lat, -105.0 as lon, true as is_current from range(1, 6) as r(i)"
    )


def test_segments_and_trip_runtimes():
    con = connect()
    _inputs(con)
    sql = render_model("core/fct_segment_traversal.sql", incremental=True)
    seg = con.execute(sql).df()
    t1 = seg[seg.trip_id == "T1"].set_index("from_stop_sequence")
    assert list(t1.index) == [1, 4]  # segments touching stop 3 are not timed to 30 s
    # Stop 1 -> 2: left at 10:00, arrived 10:02. Stop 4 -> 5: no departure window, so from arrival.
    assert t1.travel_sec.to_dict() == {1: 120, 4: 180}
    assert t1.speed_kmh.to_dict() == {1: 30.0, 4: 30.0}
    assert t1.scheduled_travel_sec.to_dict() == {1: 120, 4: 240}
    assert seg[seg.trip_id == "T2"].set_index("from_stop_sequence").speed_kmh.to_dict() == {
        1: 20.0,
        4: 22.5,
    }

    con.execute(f"create table fct_segment_traversal as {sql}")
    speeds = con.execute(
        _duckdb(render_model("marts/realtime/mart_segment_speed_by_hour.sql"))
    ).df()
    first = speeds[speeds.from_stop_id == "S1"].iloc[0]
    assert (first.n_traversals, first.p50_travel_sec, first.p90_travel_sec) == (2, 120, 180)
    assert (first.p50_speed_kmh, first.p10_speed_kmh, first.delay_ratio) == (20.0, 20.0, 1.0)
    assert (first.to_stop_name, round(first.lat, 3)) == ("Stop 2", 39.715)

    runtime = con.execute(
        _duckdb(render_model("marts/realtime/mart_trip_runtime_by_route_day.sql", incremental=True))
    ).df()
    assert len(runtime) == 1
    r = runtime.iloc[0]
    assert (r.n_trips, r.p50_runtime_min, r.p90_runtime_min, r.scheduled_runtime_min) == (
        2,
        10.0,
        12.0,
        10.0,
    )
    assert r.buffer_time_index == 0.2 and r.first_stop_name == "Stop 1"


def test_departure_window_midpoint():
    con = connect()
    _inputs(con)
    con.execute("update fct_stop_visit set arrival_method = 'shape_crossing', within_30s = true")
    sql = render_model("core/fct_segment_traversal.sql", incremental=True)
    t1 = con.execute(sql).df().query("trip_id == 'T1'").set_index("from_stop_sequence")
    # T1 left stop 2 between 10:02:20 and 10:02:40, so at 10:02:30; it reached stop 3 at 10:05.
    assert t1.loc[2, "travel_sec"] == 150


def test_sub_second_traversals_are_dropped():
    con = connect()
    _inputs(con)
    con.execute(
        "update fct_stop_visit set arrival_ts_utc = arrival_ts_utc - to_milliseconds(179500) "
        "where trip_id = 'T1' and stop_sequence = 5"
    )  # 0.5 s after leaving stop 4: whole seconds round it to 0
    seg = con.execute(render_model("core/fct_segment_traversal.sql", incremental=True)).df()
    assert set(seg[seg.trip_id == "T1"].from_stop_sequence) == {1}
