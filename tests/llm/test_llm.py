from __future__ import annotations

from whyline.llm import adapt_sql_for_engine, build_schema_brief
from whyline.semantics.dbt_artifacts import ModelInfo, RelationshipHint


def test_adapt_sql_for_duckdb_date_sub() -> None:
    sql = "SELECT route_id FROM agg_reliability_by_route_day WHERE service_date_mst >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
    expected = "SELECT route_id FROM agg_reliability_by_route_day WHERE service_date_mst >= CURRENT_DATE() - INTERVAL '30' DAY"
    assert adapt_sql_for_engine(sql, "duckdb") == expected


def test_adapt_sql_other_engines_passthrough() -> None:
    sql = "SELECT 1"
    assert adapt_sql_for_engine(sql, "bigquery") == sql


def test_adapt_sql_bigquery_qualifies_models_with_hyphenated_project() -> None:
    sql = "SELECT * FROM agg_reliability_by_route_day"
    models = {
        "agg_reliability_by_route_day": ModelInfo(
            name="agg_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.agg_reliability_by_route_day",
            description=None,
        )
    }
    result = adapt_sql_for_engine(sql, "bigquery", models)
    assert "FROM `whyline-denver.mart_denver.agg_reliability_by_route_day`" in result


def test_adapt_sql_bigquery_qualifies_stg_dataset_correctly() -> None:
    """dim_* models live in stg_denver — fq_name must route to the right dataset."""
    sql = "SELECT stop_id, stop_name FROM dim_stop"
    models = {
        "dim_stop": ModelInfo(
            name="dim_stop",
            fq_name="whyline-denver.stg_denver.dim_stop",
            description=None,
        )
    }
    result = adapt_sql_for_engine(sql, "bigquery", models)
    assert "FROM `whyline-denver.stg_denver.dim_stop`" in result


def test_adapt_sql_bigquery_leaves_already_qualified_tables_alone() -> None:
    sql = "SELECT * FROM `whyline-denver.mart_denver.agg_reliability_by_route_day`"
    models = {
        "agg_reliability_by_route_day": ModelInfo(
            name="agg_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.agg_reliability_by_route_day",
            description=None,
        )
    }
    result = adapt_sql_for_engine(sql, "bigquery", models)
    assert result == sql


def test_build_schema_brief_layer_prefix_and_join_hints() -> None:
    models = {
        "dim_stop": ModelInfo(
            name="dim_stop",
            fq_name="whyline-denver.stg_denver.dim_stop",
            description="Stop reference",
            layer="dim",
            columns={},
        ),
        "agg_reliability_by_route_day": ModelInfo(
            name="agg_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.agg_reliability_by_route_day",
            description="Daily route reliability",
            layer="agg",
            columns={},
            relationships=[RelationshipHint(to_model="dim_route", join_on="route_id")],
        ),
    }
    brief = build_schema_brief(models)
    assert "[agg] agg_reliability_by_route_day" in brief
    assert "JOIN dim_route ON route_id" in brief
    assert "[dim] dim_stop" in brief
