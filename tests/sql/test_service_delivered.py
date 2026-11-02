"""Missed trips (WP3): stream health windows and scheduled-trip outcomes, run in DuckDB."""

from __future__ import annotations

import pandas as pd
from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

DUCKDB = (
    ("timestamp(date_sub(current_date, interval 3 day))", "cast(current_date - 3 as timestamptz)"),
    ("generate_timestamp_array(", "generate_series("),
    (")) as window_start_utc", ")) as t(window_start_utc)"),
    (
        "timestamp_seconds(div(unix_seconds(feed_ts_utc), 900) * 900)",
        "to_timestamp((cast(epoch(feed_ts_utc) as bigint) // 900) * 900)",
    ),
)


def _ts(clock: str, days_ago: int = 1) -> str:
    return f"cast(current_date - {days_ago} as timestamptz) + interval '{clock}'"


def test_stream_health_counts_feed_updates_per_window():
    con = connect()
    # Updates every 30 s yesterday, except only 10 from 12:00 to 12:14 UTC.
    con.execute(
        f"""
        create table stg_rt_vehicle_positions as
        select {_ts('00:00:00')} + to_seconds(s) as feed_ts_utc
        from range(0, 86400, 30) as r(s)
        where s not between 43200 and 44099 or s < 43500
        """
    )
    rows = con.execute(
        render_model("core/fct_stream_health.sql", incremental=True, replacements=DUCKDB)
    ).df()
    rows["clock"] = rows.window_start_utc.dt.strftime("%Y-%m-%d %H:%M")
    yesterday = (pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    w = rows.set_index("clock")
    assert (
        w.loc[f"{yesterday} 11:45", "n_feed_updates"] == 30
        and w.loc[f"{yesterday} 11:45", "is_healthy"]
    )
    assert (
        w.loc[f"{yesterday} 12:00", "n_feed_updates"] == 10
        and not w.loc[f"{yesterday} 12:00", "is_healthy"]
    )
    assert not rows[rows.n_feed_updates == 0].is_healthy.any()  # windows with no data at all
    assert rows.window_start_utc.is_unique and rows.window_start_utc.min().hour == 0


def test_each_scheduled_trip_gets_one_outcome():
    con = connect()
    # (route, trip, first departure, last arrival) in UTC.
    trips = [(f"A{i}", "14:10:00", "14:40:00") for i in range(1, 6)]  # delivered
    trips += [
        ("B", "14:10:00", "14:40:00"),  # canceled
        ("C", "14:10:00", "14:40:00"),  # visits from predictions only: no vehicle
        ("D", "14:10:00", "14:40:00"),  # a vehicle reported, but no stop was reached
        ("E", "14:10:00", "14:40:00"),  # never seen in either feed
        ("F", "19:10:00", "19:40:00"),  # never seen, during an outage
    ]
    trips = [("15", *t) for t in trips]
    # A route whose vehicles never report: tracked trips, none with a vehicle.
    trips += [("N", "N1", "14:10:00", "14:40:00"), ("N", "N2", "14:20:00", "14:50:00")]
    con.execute(
        "create table fct_scheduled_stop_time as "
        + " union all ".join(
            f"select cast(current_date - 1 as date) as service_date_mst, '{t}' as trip_id, '{r}' as route_id, "
            f"0 as direction_id, {_ts(a)} as sched_departure_ts_mst, {_ts(b)} as sched_arrival_ts_mst"
            for r, t, a, b in trips
        )
    )
    con.execute(
        "create table fct_trip_status as select cast(current_date - 1 as date) as service_date, * "
        "from (values ('15', 'A1', 'completed', true), ('15', 'A2', 'partial', true), "
        "('15', 'A3', 'completed', true), ('15', 'A4', 'completed', true), "
        "('15', 'A5', 'completed', true), ('15', 'B', 'canceled', false), "
        "('15', 'C', 'completed', false), ('15', 'D', 'vanished', true), "
        "('N', 'N1', 'vanished', false), ('N', 'N2', 'partial', false)) "
        "as t(route_id, trip_id, outcome, had_vehicle)"
    )
    con.execute(
        f"""
        create table fct_stream_health as
        select cast(w as date) as window_date_utc, w as window_start_utc,
               not (w >= {_ts('19:00:00')} and w < {_ts('19:15:00')}) as is_healthy
        from (select unnest(generate_series({_ts('00:00:00')}, {_ts('23:45:00')}, interval 15 minute)) as w)
        """
    )
    sql = render_model("marts/realtime/mart_service_delivered_by_route_day.sql", incremental=True)
    rows = con.execute(sql).df()
    route = rows[rows.route_id == "15"]
    assert route.period.is_unique
    morning = route[route.n_scheduled == 9].iloc[0]
    counts = ("n_delivered", "n_canceled", "n_no_vehicle", "n_vehicle_no_visits", "n_not_tracked")
    assert tuple(morning[c] for c in counts) == (5, 1, 1, 1, 1)
    assert morning.stream_healthy and morning.n_observable == 9
    assert abs(morning.pct_tracked_with_vehicle - 6 / 7) < 1e-9  # canceled trips don't count
    assert (morning.pct_delivered, morning.pct_missed_likely) == (5 / 9, 3 / 9)
    unreported = rows[rows.route_id == "N"].iloc[0]
    assert unreported.n_no_vehicle == 2 and unreported.pct_tracked_with_vehicle == 0
    assert pd.isna(unreported.pct_delivered) and pd.isna(unreported.pct_missed_likely)
    outage = route[route.n_scheduled == 1].iloc[0]
    assert outage.n_not_tracked == 1 and outage.n_observable == 0 and not outage.stream_healthy
    assert pd.isna(outage.pct_delivered) and pd.isna(outage.pct_missed_likely)
