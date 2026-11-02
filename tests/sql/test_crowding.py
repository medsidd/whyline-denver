"""Crowding (WP2): occupancy reports assigned to stops, rolled up by trip and stop, in DuckDB."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

DATES = (("timestamp(date_", "(date_"),)


def _ts(clock: str) -> str:
    return f"cast(current_date - 1 as timestamp) + interval '{clock}'"


def _inputs(con):
    # Trip stops: (trip, seq, stop, role, dist_m, arrival). T1 loops back past S2 as seq 4.
    stops = [
        (trip, seq, stop, role, dist, f"10:0{seq}:00")
        for trip in ("T1", "T2", "T3", "T4")
        for seq, stop, role, dist in (
            (1, "S1", "first", 0),
            (2, "S2", "middle", 500),
            (3, "S3", "middle", 1000),
            (4, "S2", "last", 1500),
        )
    ]
    con.execute(
        "create table fct_stop_visit as "
        + " union all ".join(
            f"select cast(current_date - 1 as date) as service_date, '{t}' as trip_id, {q} as stop_sequence, "
            f"'{s}' as stop_id, '{r}' as stop_role, '15' as route_id, 0 as direction_id, "
            f"{d}.0 as stop_dist_m, {_ts(a)} as arrival_ts_utc, {_ts(a)} as scheduled_arrival_ts"
            for t, q, s, r, d, a in stops
        )
    )
    reports = [
        # (trip, ts, stop, dist, occupancy, valid)
        ("T1", "10:00:30", "S2", 300, "MANY_SEATS_AVAILABLE", True),
        ("T1", "10:01:50", "S2", 520, "FEW_SEATS_AVAILABLE", True),  # stopped, 20 m past
        ("T1", "10:02:30", "S3", 800, "STANDING_ROOM_ONLY", True),
        ("T1", "10:03:10", "S2", 1200, "NO_DATA_AVAILABLE", True),  # second pass: seq 4
        ("T1", "10:03:30", "S2", 1300, "FEW_SEATS_AVAILABLE", True),
        ("T1", "10:03:40", "S2", 1400, "CRUSHED_STANDING_ROOM_ONLY", False),  # not valid
        ("T3", "10:02:30", "S3", 800, "NO_DATA_AVAILABLE", True),  # reports, but no data
        ("T4", "10:01:00", "S2", 400, "MANY_SEATS_AVAILABLE", True),
        ("T9", "10:01:00", "S2", 400, "FULL", True),  # trip with no visits
    ]
    con.execute(
        "create table stg_rt_vehicle_positions as "
        + " union all ".join(
            f"select cast(current_date - 1 as date) as service_date, {_ts(ts)} as feed_ts_utc, "
            f"'{t}' as trip_id, 'V-{t}' as vehicle_id, {_ts(ts)} as report_ts_utc, '{s}' as stop_id, "
            f"{d}.0 as dist_along_m, '{o}' as occupancy_status, {v} as valid_for_timing"
            for t, ts, s, d, o, v in reports
        )
    )
    con.execute(
        "create table dim_stop as select * from (values ('S1', 'First', 39.7, -105.0, true), "
        "('S2', 'Second', 39.71, -105.0, true), ('S3', 'Third', 39.72, -105.0, true)) "
        "as t(stop_id, stop_name, lat, lon, is_current)"
    )


def test_reports_reach_the_right_stop_and_roll_up():
    con = connect()
    _inputs(con)
    sql = render_model("core/fct_trip_occupancy.sql", incremental=True, replacements=DATES)
    rows = con.execute(sql).df()
    assert len(rows) == 16 and "T9" not in set(rows.trip_id)  # every visit, nothing else

    t1 = rows[rows.trip_id == "T1"].set_index("stop_sequence")
    assert t1.n_reports.to_dict() == {1: 0, 2: 2, 3: 1, 4: 2}
    assert t1.n_reports_with_data.to_dict() == {1: 0, 2: 2, 3: 1, 4: 1}
    assert t1.max_level.dropna().astype(int).to_dict() == {2: 2, 3: 3, 4: 2}
    assert t1.loc[3, "max_level_label"] == "standing_room_only"
    t3 = rows[rows.trip_id == "T3"].set_index("stop_sequence")
    assert t3.loc[3, "n_reports"] == 1 and t3.max_level.isna().all()

    con.execute(f"create table fct_trip_occupancy as {sql}")
    hourly = con.execute(render_model("marts/realtime/mart_crowding_by_route_hour.sql")).df()
    assert len(hourly) == 1
    h = hourly.iloc[0]
    assert (h.n_trips, h.n_trips_with_data, h.pct_trips_with_data) == (4, 2, 0.5)
    assert (h.pct_trips_few_seats_or_worse, h.pct_trips_standing_or_worse) == (0.5, 0.5)
    assert h.peak_stop_id_mode == "S3"  # T1 peaked there; T4 never passed many seats

    by_stop = con.execute(render_model("marts/realtime/mart_crowding_by_stop.sql")).df()
    s3 = by_stop[by_stop.stop_id == "S3"].iloc[0]
    assert (s3.n_visits, s3.n_visits_with_data, s3.pct_standing_or_worse) == (4, 1, 1.0)
    assert s3.stop_name == "Third"
    s2 = by_stop[by_stop.stop_id == "S2"]  # both passes of the loop, all in one hour
    assert s2.n_visits.sum() == 8 and s2.n_visits_with_data.sum() == 3
    assert set(by_stop.day_type) <= {"weekday", "weekend"}
