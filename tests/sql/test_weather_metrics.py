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
    # Only the percentile and clock syntax differ for this offline execution.
    return (
        sql.replace("current_timestamp()", "current_timestamp")
        .replace('date_sub(current_date("America/Denver"), interval 30 day)', "DATE '2026-09-15'")
        .replace("approx_quantiles(delay_sec, 100)[offset(50)]", "quantile_cont(delay_sec, 0.5)")
        .replace("approx_quantiles(delay_sec, 100)[offset(90)]", "quantile_cont(delay_sec, 0.9)")
    )


def test_missing_weather_is_unknown_and_excluded_from_weather_comparison():
    with duckdb.connect() as con:
        con.execute(
            """
            CREATE TABLE fct_trip_observation AS
            SELECT * FROM (VALUES
                ('15', DATE '2026-10-01', 0, 0),
                ('15', DATE '2026-10-02', 600, 600),
                ('15', DATE '2026-10-03', 600, 600),
                ('15', DATE '2026-10-04', 600, 600)
            ) e(route_id, service_date_mst, delay_sec, delay_sec_raw);
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
