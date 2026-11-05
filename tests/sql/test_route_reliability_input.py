"""Exercise the route mart's input selection offline against representative events."""

from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined

MODEL = (
    Path(__file__).resolve().parents[2]
    / "dbt/models/marts/reliability/mart_reliability_by_route_day.sql"
)


@pytest.mark.parametrize("incremental", [False, True])
def test_route_metrics_exclude_unassigned_and_unpublished_visits(incremental):
    # SQL templates must not HTML-escape operators or quoted strings.
    template = Environment(autoescape=False, undefined=StrictUndefined).from_string(  # noqa: S701
        MODEL.read_text()
    )
    sql = template.render(
        config=lambda **kwargs: "",
        ref=lambda name: name,
        var=lambda name, default: {"stream_first_full_date": "2000-01-01"}.get(name, default),
        is_incremental=lambda: incremental,
    )
    # Execute the production input CTE without the BigQuery-only aggregations.
    input_sql = sql[sql.index("with e as (") : sql.index(",\nw as (")]
    input_sql = input_sql.replace(
        'date_sub(current_date("America/Denver"), interval 30 day)',
        "current_date - interval 30 day",
    )
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE fct_stop_visit AS "
            "SELECT * FROM (VALUES "
            "('15', current_date, 60, 'shape_crossing', 30, true, false, 'stream_v1'), "
            "('15', current_date, 600, 'shape_crossing_gap', 90, false, false, 'stream_v1'), "
            "(NULL, current_date, 900, 'shape_crossing', 30, true, false, 'stream_v1'), "
            "('0', current_date, NULL, 'skipped', NULL, NULL, true, 'stream_v1'), "
            "('15', current_date, 120, 'backfill_shape_crossing', 900, false, false, 'backfill_v1'), "
            "('old', current_date - interval 45 day, 120, 'shape_crossing', 30, true, false, 'stream_v1')"
            ") AS v(route_id, service_date, delay_sec, arrival_method, arrival_window_sec, "
            "within_30s, skipped, data_version)"
        )
        rows = con.execute(
            input_sql + " SELECT route_id, count(*), avg(delay_sec) FROM e "
            "GROUP BY route_id ORDER BY route_id"
        ).fetchall()
    # Unassigned routes and unpublished backfill rows never reach route metrics.
    expected = [("0", 1, None), ("15", 2, 330.0)]
    if not incremental:
        expected.append(("old", 1, 120.0))
    assert rows == expected


@pytest.mark.parametrize(
    ("mart", "cte", "next_cte"),
    [
        ("mart_reliability_by_route_day", "e", "w"),
        ("mart_reliability_by_stop_hour", "base", "headways"),
    ],
)
@pytest.mark.parametrize(
    ("publish_backfill", "expected"),
    [(False, ["2026-10-29"]), (True, ["2026-10-28", "2026-10-29"])],
)
def test_partial_first_stream_day_stays_on_the_legacy_method(
    mart, cte, next_cte, publish_backfill, expected
):
    sql = (
        Environment(autoescape=False, undefined=StrictUndefined)  # noqa: S701
        .from_string((MODEL.parent / f"{mart}.sql").read_text())
        .render(
            config=lambda **kwargs: "",
            ref=lambda name: name,
            var=lambda name, default: {"publish_backfill": publish_backfill}.get(name, default),
            is_incremental=lambda: False,
        )
    )
    input_sql = sql[sql.index(f"with {cte} as (") : sql.index(f",\n{next_cte} as (")]
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE fct_stop_visit AS SELECT * FROM (VALUES "
            "('15', 's1', 0, DATE '2026-10-28', 2, TIMESTAMP '2026-10-29 08:45:00', 60, 900, "
            "'shape_crossing', 30, true, false, 'stream_v1'), "
            "('15', 's1', 0, DATE '2026-10-29', 8, TIMESTAMP '2026-10-29 14:00:00', 60, 900, "
            "'shape_crossing', 30, true, false, 'stream_v1')"
            ") AS v(route_id, stop_id, direction_id, service_date, arrival_hour_mst, arrival_ts_utc, "
            "delay_sec, scheduled_headway_sec, arrival_method, arrival_window_sec, within_30s, "
            "skipped, data_version)"
        )
        rows = con.execute(
            input_sql + f" SELECT DISTINCT service_date_mst::varchar FROM {cte} ORDER BY 1"
        ).fetchall()
    assert [r[0] for r in rows] == expected
