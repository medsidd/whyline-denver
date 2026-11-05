"""Veo availability near stops (WP14), run in DuckDB with planar stand-ins for the GIS calls."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

GIS = """
create or replace macro st_dwithin(a, b, d) as
    6371000 * 2 * asin(sqrt(
        pow(sin(radians(b.lat - a.lat) / 2), 2)
        + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2)
    )) <= d;
create or replace macro st_contains(area, point) as point.lon < -104.9;  -- "Denver" is west of -104.9
create or replace macro st_union_agg(g) as first(g);
"""
DUCKDB = (
    ("timestamp(date_sub(current_date, interval 2 day))", "cast(current_date - 2 as timestamptz)"),
    ("timestamp(date_add(current_date, interval 2 day))", "cast(current_date + 2 as timestamptz)"),
    (
        "cross join unnest(['scooter', 'bicycle']) as form_factor",
        "cross join (select unnest(['scooter', 'bicycle']) as form_factor)",
    ),
)


def test_availability_counts_zero_snapshots():
    con = connect()
    con.execute(GIS)
    # Two snapshots 15 minutes apart, yesterday at 18:00 UTC (11:00 or 12:00 in Denver).
    t1 = "cast(current_date - 1 as timestamptz) + interval '18:00:00'"
    t2 = "cast(current_date - 1 as timestamptz) + interval '18:15:00'"
    near1 = "{'lon': -104.9900, 'lat': 39.7400}"  # at stop S1
    near2 = "{'lon': -104.9950, 'lat': 39.7500}"  # at stop S2, about 1.1 km north
    con.execute(
        f"""
        create table stg_gbfs_veo_vehicles as select * from (values
            ({t1}, 'scooter', {near1}, true),
            ({t1}, 'bicycle', {near1}, true), ({t2}, 'bicycle', {near1}, true),
            ({t1}, 'bicycle', {near2}, true), ({t2}, 'bicycle', {near2}, true),
            ({t2}, 'scooter', {near2}, false)  -- reserved
        ) as t(snapshot_ts_utc, form_factor, geom, is_available)
        """
    )
    con.execute(
        f"""
        create table dim_stop as select * from (values
            ('S1', 'First', 39.74, -104.99, {near1}, true),
            ('S2', 'Second', 39.75, -104.995, {near2}, true),
            ('S3', 'Aurora', 39.74, -104.80, {{'lon': -104.80, 'lat': 39.74}}, true)
        ) as t(stop_id, stop_name, lat, lon, geom, is_current)
        """
    )
    con.execute(f"create table dim_tract as select {near1} as geom")
    sql = render_model(
        "core/fct_micromobility_near_stop.sql", incremental=True, replacements=DUCKDB
    )
    rows = con.execute(sql).df().set_index(["stop_id", "form_factor"])
    assert set(rows.index.get_level_values(0)) == {"S1", "S2"}  # S3 is outside the service area
    assert (rows.n_snapshots == 2).all()
    s1 = rows.loc[("S1", "scooter")]
    assert (s1.avg_available_within_200m, s1.pct_snapshots_none_within_200m) == (0.5, 0.5)
    s2 = rows.loc[("S2", "scooter")]  # only a reserved scooter: none available
    assert (s2.avg_available_within_200m, s2.pct_snapshots_none_within_200m) == (0.0, 1.0)
    assert rows.loc[("S2", "bicycle"), "avg_available_within_200m"] == 1.0

    con.execute(f"create table fct_micromobility_near_stop as {sql}")
    mart = con.execute(render_model("marts/access/mart_micromobility_access_by_stop.sql")).df()
    first = mart.set_index("stop_id").loc["S1"]
    assert (first.avg_scooters_within_200m, first.pct_time_no_scooter, first.stop_name) == (
        0.5,
        0.5,
        "First",
    )
    assert first.period == "midday"
