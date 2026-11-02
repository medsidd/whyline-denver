"""Service alerts (WP8): alert history, entity periods, stop closures and route-day hours, in DuckDB."""

from __future__ import annotations

import pandas as pd
from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

LATEST = (
    (
        """array_agg(
            struct(cause, effect, header_text, description_text, url)
            order by feed_ts_utc desc limit 1
        )[offset(0)]""",
        "arg_max({'cause': cause, 'effect': effect, 'header_text': header_text, "
        "'description_text': description_text, 'url': url}, feed_ts_utc)",
    ),
)
DAYS = (
    ("timestamp(d, 'America/Denver')", "timezone('America/Denver', cast(d as timestamp))"),
    (
        "timestamp(date_add(d, interval 1 day), 'America/Denver')",
        "timezone('America/Denver', cast(d + interval 1 day as timestamp))",
    ),
    (
        "from unnest(generate_date_array(date '2026-11-02', current_date)) as d",
        "from (select cast(unnest(generate_series(current_date - 1, current_date, interval 1 day)) as date) as d)",
    ),
)


NOW = pd.Timestamp.now(tz="UTC").floor("min")


def ago(minutes: int) -> str:
    """A fixed timestamp minutes before now (after, when negative), equal across statements."""
    return f"timestamptz '{(NOW - pd.Timedelta(minutes=minutes)).isoformat()}'"


def _snapshots(con):
    """Alert A: stop S1 closed, period edited between snapshots, still in the feed.
    Alert B: detour naming route 15 only, no period, left the feed two hours ago."""
    alerts, periods = [], []
    for minutes in (240, 120, 15):
        text = "Stop closed (updated)" if minutes == 15 else "Stop closed"
        alerts.append(f"({ago(minutes)}, 'A', 'CONSTRUCTION', 'NO_SERVICE', '{text}', '15', 'S1')")
        end = f"{ago(-600)}" if minutes == 15 else f"{ago(-60)}"  # RTD extended it
        periods.append(f"({ago(minutes)}, 'A', {ago(300)}, {end})")
    for minutes in (240, 180, 135):
        alerts.append(f"({ago(minutes)}, 'B', null, 'DETOUR', 'Detour', '15', null)")
    con.execute(
        "create table stg_rt_alerts as select feed_ts_utc, alert_id, cause, effect, header_text, "
        "null::varchar as description_text, null::varchar as url, null::varchar as agency_id, route_id, "
        "3 as route_type, null::int as direction_id, stop_id::varchar as stop_id, null::varchar as trip_id "
        "from (values "
        + ", ".join(alerts)
        + ") as t(feed_ts_utc, alert_id, cause, effect, header_text, route_id, stop_id)"
    )
    con.execute(
        "create table stg_rt_alert_periods as select * from (values "
        + ", ".join(periods)
        + ") as t(feed_ts_utc, alert_id, active_start_utc, active_end_utc)"
    )
    con.execute(
        "create table dim_stop as select 'S1' as stop_id, 'First' as stop_name, 39.7 as lat, "
        "-105.0 as lon, true as is_current"
    )


def test_alert_history_closures_and_hours():
    con = connect()
    _snapshots(con)
    # A was already known from an earlier night, first seen a day ago.
    con.execute(
        f"create table fct_alert as select 'A' as alert_id, {ago(1440)} as first_seen_ts, "
        f"{ago(1000)} as last_seen_ts, 'CONSTRUCTION' as cause, 'NO_SERVICE' as effect, "
        "'old' as header_text, null::varchar as description_text, null::varchar as url"
    )
    alerts = (
        con.execute(
            render_model(
                "core/fct_alert.sql", incremental=True, this="fct_alert", replacements=LATEST
            )
        )
        .df()
        .set_index("alert_id")
    )
    assert alerts.loc["A", "header_text"] == "Stop closed (updated)"  # the latest snapshot's text
    assert alerts.loc["A", "first_seen_ts"] < alerts.loc["B", "first_seen_ts"]  # kept from before
    con.execute("drop table fct_alert")
    fresh = alerts.reset_index()  # noqa: F841 - read by DuckDB below
    con.execute("create table fct_alert as select * from fresh")

    periods = con.execute(render_model("core/fct_alert_entity_period.sql")).df()
    a_rows = periods[periods.alert_id == "A"]
    assert len(a_rows) == 2  # the original period and RTD's extension
    assert periods.alert_entity_period_key.is_unique
    con.execute("create table fct_alert_entity_period as select * from periods")

    closures = (
        con.execute(render_model("marts/disruptions/mart_stop_closures.sql"))
        .df()
        .set_index("alert_id")
    )
    a = closures.loc["A"]
    assert (a.stop_id, a.is_closure, a.is_active_now, a.stop_name) == ("S1", True, True, "First")
    # Only the last snapshot's period counts: the extended end, not the first.
    assert a.until_ts > pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=500)
    assert "B" not in closures.index  # names no stop

    days = con.execute(
        render_model("marts/disruptions/mart_alerts_by_route_day.sql", replacements=DAYS)
    ).df()
    detour = days[days.effect == "DETOUR"]
    # B ran from first seen (240 min ago) to 15 min after it was last seen (135 min ago).
    assert abs(detour.alert_hours.sum() - (240 - 120) / 60) < 0.02
    closed = days[days.effect == "NO_SERVICE"]
    assert closed.n_stops_named.max() == 1 and set(closed.n_alerts) == {1}
