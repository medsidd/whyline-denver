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
def test_route_metrics_exclude_unassigned_events(incremental):
    # SQL templates must not HTML-escape operators or quoted strings.
    template = Environment(autoescape=False, undefined=StrictUndefined).from_string(  # noqa: S701
        MODEL.read_text()
    )
    sql = template.render(
        config=lambda **kwargs: "",
        ref=lambda name: name,
        var=lambda name, default: default,
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
            "CREATE TABLE int_rt_events_resolved AS "
            "SELECT * FROM (VALUES "
            "('15', current_date, 60, 60), "
            "('15', current_date, 600, 600), "
            "(NULL, current_date, 900, 900), "
            "('0', current_date, 0, NULL), "
            "('old', current_date - interval 45 day, 120, 120)"
            ") AS events(route_id, service_date_mst, delay_sec, delay_sec_raw)"
        )
        rows = con.execute(
            input_sql + " SELECT route_id, count(*), avg(delay_sec) FROM e "
            "GROUP BY route_id ORDER BY route_id"
        ).fetchall()
    expected = [("0", 1, 0.0), ("15", 2, 330.0)]
    if not incremental:
        expected.append(("old", 1, 120.0))
    assert rows == expected
