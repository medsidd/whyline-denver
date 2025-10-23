from __future__ import annotations

from whylinedenver.llm import adapt_sql_for_engine


def test_adapt_sql_for_duckdb_date_sub() -> None:
    sql = "SELECT route_id FROM mart_reliability_by_route_day WHERE service_date_mst >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
    expected = "SELECT route_id FROM mart_reliability_by_route_day WHERE service_date_mst >= CURRENT_DATE() - INTERVAL '30' DAY"
    assert adapt_sql_for_engine(sql, "duckdb") == expected


def test_adapt_sql_other_engines_passthrough() -> None:
    sql = "SELECT 1"
    assert adapt_sql_for_engine(sql, "bigquery") == sql
