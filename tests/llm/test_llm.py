from __future__ import annotations

from whyline.llm import adapt_sql_for_engine
from whyline.semantics.dbt_artifacts import ModelInfo


def test_adapt_sql_for_duckdb_date_sub() -> None:
    sql = "SELECT route_id FROM mart_reliability_by_route_day WHERE service_date_mst >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
    expected = "SELECT route_id FROM mart_reliability_by_route_day WHERE service_date_mst >= CURRENT_DATE() - INTERVAL '30' DAY"
    assert adapt_sql_for_engine(sql, "duckdb") == expected


def test_adapt_sql_other_engines_passthrough() -> None:
    sql = "SELECT 1"
    assert adapt_sql_for_engine(sql, "bigquery") == sql


def test_adapt_sql_bigquery_qualifies_models_with_hyphenated_project() -> None:
    sql = "SELECT * FROM mart_reliability_by_route_day"
    models = {
        "mart_reliability_by_route_day": ModelInfo(
            name="mart_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.mart_reliability_by_route_day",
            description=None,
        )
    }
    result = adapt_sql_for_engine(sql, "bigquery", models)
    assert "FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`" in result


def test_adapt_sql_bigquery_leaves_already_qualified_tables_alone() -> None:
    sql = "SELECT * FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`"
    models = {
        "mart_reliability_by_route_day": ModelInfo(
            name="mart_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.mart_reliability_by_route_day",
            description=None,
        )
    }
    result = adapt_sql_for_engine(sql, "bigquery", models)
    assert result == sql
