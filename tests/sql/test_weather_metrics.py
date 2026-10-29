import re
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined


def render_model(name):
    root = Path(__file__).resolve().parents[2] / "dbt/models/marts/reliability"
    env = Environment(autoescape=False, undefined=StrictUndefined)  # noqa: S701 - SQL, not HTML
    sql = env.from_string((root / f"{name}.sql").read_text()).render(
        config=lambda **kwargs: "",
        ref=lambda name: name,
        var=lambda name, default: default,
        is_incremental=lambda: False,
    )
    # Only the percentile, clock, array and column-list syntax differ for this offline execution.
    sql = re.sub(
        r"approx_quantiles\((\w+), 100\)\[offset\((\d+)\)\]",
        lambda m: f"quantile_cont({m[1]}, {int(m[2]) / 100})",
        sql,
    )
    return (
        sql.replace("current_timestamp()", "current_timestamp")
        .replace('date_sub(current_date("America/Denver"), interval 30 day)', "DATE '2026-09-15'")
        .replace('current_date("America/Denver")', "current_date")
        .replace(",\n            second\n        )", ", 'second')")
        .replace(" limit 1)[offset(0)]", ")[1]")
        .replace("agg.* except (", "agg.* exclude (")
    )


def visits(con, rows):
    """rows: (route_id, service_date, delay_sec); every visit a 30 s shape crossing."""
    con.execute("CREATE MACRO safe_divide(a, b) AS a / nullif(b, 0)")
    con.execute(
        "CREATE TABLE fct_stop_visit (route_id varchar, service_date date, delay_sec int, "
        "arrival_method varchar, arrival_window_sec int, within_30s boolean, skipped boolean, "
        "data_version varchar)"
    )
    for route, day, delay in rows:
        con.execute(
            "INSERT INTO fct_stop_visit VALUES (?, ?, ?, 'shape_crossing', 30, true, false, 'stream_v1')",
            [route, day, delay],
        )
    con.execute(
        "CREATE TABLE fct_scheduled_stop_time AS "
        "SELECT '15' AS route_id, DATE '2026-10-01' AS service_date_mst FROM range(8)"
    )
    con.execute(
        "CREATE TABLE fct_trip_status AS SELECT * FROM (VALUES "
        "('15', DATE '2026-10-01', 'canceled', 'stream_v1'), ('15', DATE '2026-10-01', 'completed', 'stream_v1')"
        ") t(route_id, service_date, outcome, data_version)"
    )


def test_missing_weather_is_unknown_and_excluded_from_weather_comparison():
    with duckdb.connect() as con:
        visits(
            con,
            [
                ("15", "2026-10-01", 0),
                ("15", "2026-10-02", 600),
                ("15", "2026-10-03", 600),
                ("15", "2026-10-04", 600),
            ],
        )
        con.execute(
            """
            CREATE TABLE fct_weather_daily AS
            SELECT * FROM (VALUES
                (DATE '2026-10-01', 'USW00003017', 'none', false),
                (DATE '2026-10-02', 'USW00003017', 'light', false),
                (DATE '2026-10-03', 'OTHER', 'heavy', true),
                (DATE '2026-10-04', 'USW00003017', NULL, NULL)
            ) w(weather_date, station, precip_bin, snow_day);
            CREATE TABLE dim_route AS
            SELECT * FROM (VALUES
                ('15', '15', 'Old name', false),
                ('15', '15', 'East Colfax', true)
            ) r(route_id, route_name, route_long_name, is_latest_version);
        """
        )
        con.execute(
            "CREATE TABLE mart_reliability_by_route_day AS "
            + render_model("mart_reliability_by_route_day")
        )
        rows = con.execute(
            "SELECT precip_bin, snow_day, route_long_name FROM mart_reliability_by_route_day "
            "ORDER BY service_date_mst"
        ).fetchall()
        # Other stations are ignored; names come from the latest route version only.
        assert rows == [
            ("none", False, "East Colfax"),
            ("light", False, "East Colfax"),
            ("unknown", None, "East Colfax"),
            ("unknown", None, "East Colfax"),
        ]
        con.execute(
            "INSERT INTO mart_reliability_by_route_day "
            "BY NAME SELECT '15' AS route_id, DATE '2026-01-01' AS service_date_mst, "
            "'none' AS precip_bin, 0.0 AS pct_on_time"
        )
        con.execute("CREATE TABLE weather_impacts AS " + render_model("mart_weather_impacts"))
        rows = con.execute(
            "SELECT precip_bin, pct_on_time_normal, delta_pct_on_time "
            "FROM weather_impacts ORDER BY precip_bin"
        ).fetchall()
        assert rows == [("light", 1.0, -1.0), ("none", 1.0, 0.0)]


def test_on_time_follows_rtd_and_unknown_delays_are_excluded():
    with duckdb.connect() as con:
        # -90 s is early, 301 s late; -30, 0 and 300 s are on time; NULL is unknown.
        visits(con, [("15", "2026-10-01", d) for d in (-90, -30, 0, 300, 301, None)])
        con.execute(
            "CREATE TABLE fct_weather_daily AS SELECT DATE '2026-10-01' AS weather_date, "
            "'USW00003017' AS station, 'none' AS precip_bin, false AS snow_day"
        )
        con.execute(
            "CREATE TABLE dim_route AS SELECT '15' AS route_id, '15' AS route_name, "
            "'East Colfax' AS route_long_name, true AS is_latest_version"
        )
        row = con.execute(
            "SELECT n_events, n_reported_events, pct_on_time, n_canceled_trips, pct_within_30s, "
            "n_scheduled, pct_observed, data_version "
            "FROM (" + render_model("mart_reliability_by_route_day") + ")"
        ).fetchone()
    assert row == (6, 5, 0.6, 1, 1.0, 8, 0.625, "stream_v1")


def test_stop_hour_headways_follow_one_route_and_direction():
    with duckdb.connect() as con:
        con.execute("CREATE MACRO safe_divide(a, b) AS a / nullif(b, 0)")
        con.execute("CREATE MACRO timestamp_diff(a, b, unit) AS epoch(a) - epoch(b)")
        # (route, arrival, delay_sec, scheduled_headway_sec); route 16 interleaves at the stop.
        rows = [
            ("15", "08:00", 0, 600),
            ("16", "08:08", 0, 900),
            ("15", "08:10", -90, 600),  # headway 600 s: adherent; early
            ("15", "08:30", None, 600),  # headway 1200 s: not adherent; delay unknown
            ("15", "08:40", 301, None),  # no scheduled headway: not judged; late
            ("15", None, None, 600),  # skipped stop: no arrival, not counted
        ]
        con.execute(
            "CREATE TABLE fct_stop_visit (stop_id varchar, route_id varchar, direction_id int, "
            "service_date date, arrival_hour_mst int, arrival_ts_utc timestamp, delay_sec int, "
            "scheduled_headway_sec int, arrival_method varchar, within_30s boolean, "
            "data_version varchar)"
        )
        for route, at, delay, headway in rows:
            con.execute(
                "INSERT INTO fct_stop_visit VALUES ('S1', ?, 0, DATE '2026-10-01', 8, "
                "CAST('2026-10-01 ' || ? AS timestamp), ?, ?, 'shape_crossing', true, 'stream_v1')",
                [route, at, delay, headway],
            )
        con.execute(
            "CREATE TABLE dim_stop AS SELECT 'S1' AS stop_id, 'Colfax & Broadway' AS stop_name, "
            "39.74 AS lat, -104.99 AS lon, true AS is_latest_version"
        )
        con.execute(
            "CREATE TABLE dim_route AS SELECT '15' AS route_id, '15' AS route_name, "
            "true AS is_latest_version"
        )
        row = con.execute(
            "SELECT n_events, n_reported_events, pct_on_time, headway_adherence_rate, "
            "obs_headway_sec_p50, route_id_mode, data_version "
            "FROM (" + render_model("mart_reliability_by_stop_hour") + ")"
        ).fetchone()
    assert row == (5, 4, 0.5, 0.5, 600.0, "15", "stream_v1")
