"""Scheduled-service marts (WP6) on a small schedule, run in DuckDB."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

UNNEST_BLOCKS = (
    ("unnest(generate_array(0, 4)) as block", "unnest(range(0, 5)) as t(block)"),
    ("div(hour_mst - 6, 3)", "(hour_mst - 6) // 3"),
)


def _schedule(con):
    # Next Wednesday, Saturday and Sunday (DuckDB dayofweek: Sunday = 0).
    con.execute(
        """
        create table sample_days as
        select current_date + cast((dow - dayofweek(current_date) + 7) % 7 as int) as d
        from (values (3), (6), (0)) as v(dow)
        """
    )

    def departures(route, direction, stop, first, last, every, days="select d from sample_days"):
        """Departures from `first` to `last` (local HH:MM, inclusive), every `every` minutes."""
        start, end = (int(t[:2]) * 60 + int(t[3:]) for t in (first, last))
        return f"""
        select d as service_date_mst, '{route}-' || d || '-' || m as trip_id, '{stop}' as stop_id,
               1 as stop_sequence, '{route}' as route_id, {direction} as direction_id,
               timezone('America/Denver', cast(d as timestamp) + to_minutes(m)) as sched_departure_ts_mst
        from ({days}), range({start}, {end} + 1, {every}) as r(m)
        """

    con.execute(
        "create table fct_scheduled_stop_time as "
        + " union all ".join(
            [
                departures("F", 0, "S1", "05:00", "23:00", 10),
                departures("F", 1, "S1", "05:00", "23:00", 10),
                departures(
                    "F", 0, "S2", "07:00", "19:00", 20
                ),  # short turn: fewer departures than S1
                # Weekday only, every 30 minutes.
                departures(
                    "I",
                    0,
                    "S3",
                    "06:00",
                    "22:00",
                    30,
                    "select min(d) as d from sample_days where dayofweek(d) = 3",
                ),
                # Every 10 minutes, except a 12:00-14:59 block averaging every 20 minutes.
                departures("G", 0, "S4", "05:00", "11:50", 10),
                departures("G", 0, "S4", "12:00", "14:59", 20),
                departures("G", 0, "S4", "15:00", "23:00", 10),
            ]
        )
    )
    con.execute(
        "create table dim_stop as select * from (values ('S1', 'First', 39.7, -105.0, true), "
        "('S2', 'Second', 39.71, -105.0, true), ('S3', 'Third', 39.72, -105.0, true), "
        "('S4', 'Fourth', 39.73, -105.0, true)) as t(stop_id, stop_name, lat, lon, is_current)"
    )
    con.execute(
        "create table dim_route as select * from (values ('F', 'F', 'Frequent', true), "
        "('I', 'I', 'Infrequent', true), ('G', 'G', 'Gap', true)) "
        "as t(route_id, route_name, route_long_name, is_latest_version)"
    )


def test_stop_frequency_counts_departures_per_hour():
    con = connect()
    _schedule(con)
    rows = con.execute(render_model("marts/service/mart_service_frequency_by_stop.sql")).df()
    weekday_f = rows[(rows.route_id == "F") & (rows.stop_id == "S1") & (rows.day_type == "weekday")]
    assert set(weekday_f.direction_id) == {0, 1}
    at_8 = weekday_f[(weekday_f.direction_id == 0) & (weekday_f.hour_mst == 8)].iloc[0]
    assert (at_8.n_departures, at_8.avg_headway_min, at_8.stop_name) == (6, 10.0, "First")
    assert set(rows.day_type) == {"weekday", "saturday", "sunday"}
    assert set(rows[rows.route_id == "I"].day_type) == {"weekday"}


def test_frequent_network_needs_every_hour_direction_and_day_type():
    con = connect()
    _schedule(con)
    rows = con.execute(
        render_model("marts/service/mart_frequent_network_by_route.sql", replacements=UNNEST_BLOCKS)
    ).df()
    f = rows[(rows.route_id == "F") & (rows.direction_id == 0) & (rows.day_type == "weekday")].iloc[
        0
    ]
    assert f.busiest_stop_id == "S1"
    assert (f.first_departure, f.last_departure, f.span_hours) == ("05:00", "23:00", 18.0)
    assert (f.headway_midday_min, f.min_departures_per_3h) == (10.0, 18)
    assert bool(f.is_frequent_day) and bool(f.is_frequent_route)
    flags = rows.groupby("route_id").is_frequent_route.first().to_dict()
    assert flags == {"F": True, "I": False, "G": False}
    g = rows[rows.route_id == "G"].iloc[0]
    assert g.min_departures_per_3h == 9 and not bool(g.is_frequent_day)


def test_tract_intensity_shares_each_stop_by_population():
    con = connect()
    _schedule(con)
    con.execute(
        "create table bridge_stop_tract as select * from (values "
        "('S1', 'A', 2000, 0.75), ('S1', 'B', 1000, 0.25), ('S2', 'B', 1000, 1.0)) "
        "as t(stop_id, geoid, tract_pop_total, weighting_factor)"
    )
    rows = con.execute(render_model("marts/service/mart_service_intensity_by_tract.sql")).df()
    by_tract = rows.set_index("geoid")
    # S1: two directions x 109 weekday departures; S2: 37.
    assert by_tract.loc["A", "weekday_departures_share"] == 163.5
    assert by_tract.loc["A", "weekday_departures_per_1000_residents"] == 81.8
    assert by_tract.loc["B", "weekday_departures_share"] == 91.5
    assert tuple(by_tract.loc["B", ["n_stops_nearby", "n_frequent_stops_nearby"]]) == (2, 1)
