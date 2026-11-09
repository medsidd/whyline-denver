from __future__ import annotations

import json

import pytest

from whyline.logs import log_query
from whyline.sql_guardrails import (
    GuardrailConfig,
    SqlValidationError,
    referenced_tables,
    sanitize_sql,
)


def test_valid_query_passes_without_modification():
    sql = "SELECT stop_id FROM mart_access_score_by_stop LIMIT 10"
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    sanitized = sanitize_sql(sql, config)
    assert sanitized == sql


def test_limit_is_added_when_missing():
    sql = "SELECT stop_id FROM mart_access_score_by_stop"
    config = GuardrailConfig(
        allowed_models={"mart_access_score_by_stop"}, engine="duckdb", enforce_limit=123
    )
    sanitized = sanitize_sql(sql, config)
    assert sanitized.endswith("LIMIT 123")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM mart_access_score_by_stop",
        "SELECT * FROM mart_access_score_by_stop; DROP TABLE users",
    ],
)
def test_disallowed_statements_raise(sql: str):
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    with pytest.raises(SqlValidationError):
        sanitize_sql(sql, config)


def test_query_referencing_unauthorized_table_fails():
    sql = "SELECT * FROM mart_access_score_by_stop JOIN mart_unknown ON 1=1"
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    with pytest.raises(SqlValidationError) as exc:
        sanitize_sql(sql, config)
    assert "mart_unknown" in str(exc.value)


def test_bigquery_requires_where_when_partition_column_present():
    sql = "SELECT service_date_mst FROM mart_reliability_by_route_day"
    config = GuardrailConfig(
        allowed_models={"mart_reliability_by_route_day"},
        engine="bigquery",
        partition_columns=("service_date_mst",),
    )
    with pytest.raises(SqlValidationError) as exc:
        sanitize_sql(sql, config)
    assert "service_date_mst" in str(exc.value)


def test_cte_select_passes():
    sql = (
        "WITH base AS (\n"
        "    SELECT stop_id FROM mart_access_score_by_stop\n"
        ")\n"
        "SELECT * FROM base"
    )
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    sanitized = sanitize_sql(sql, config)
    assert sanitized.startswith("WITH base")


def test_bigquery_quotes_hyphenated_table_identifier():
    sql = "SELECT * FROM whyline-denver.mart_denver.mart_reliability_by_route_day"
    config = GuardrailConfig(
        allowed_models={"mart_reliability_by_route_day"},
        engine="bigquery",
        allowed_projects={"whyline-denver"},
        allowed_datasets={"mart_denver"},
    )
    sanitized = sanitize_sql(sql, config)
    assert "FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`" in sanitized


def test_bigquery_rejects_cross_dataset_reference():
    sql = "SELECT * FROM some_other_project.some_dataset.mart_access_score_by_stop"
    config = GuardrailConfig(
        allowed_models={"mart_access_score_by_stop"},
        engine="bigquery",
        allowed_projects={"whyline-denver"},
        allowed_datasets={"mart_denver"},
    )
    with pytest.raises(SqlValidationError) as exc:
        sanitize_sql(sql, config)
    assert "some_other_project.some_dataset.mart_access_score_by_stop" in str(exc.value)


def test_bigquery_allows_configured_namespace():
    sql = "SELECT * FROM whyline-denver.mart_denver.mart_access_score_by_stop"
    config = GuardrailConfig(
        allowed_models={"mart_access_score_by_stop"},
        engine="bigquery",
        allowed_projects={"whyline-denver"},
        allowed_datasets={"mart_denver"},
    )
    sanitized = sanitize_sql(sql, config)
    assert "mart_access_score_by_stop" in sanitized


def test_referenced_tables_skip_ctes_and_qualifiers():
    sql = (
        "WITH recent AS (SELECT * FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`) "
        "SELECT * FROM recent JOIN mart_weather_impacts USING (route_id)"
    )
    assert referenced_tables(sql) == ["mart_reliability_by_route_day", "mart_weather_impacts"]


def test_query_log_records_marts_status_and_ready_made_question(tmp_path):
    path = tmp_path / "queries.jsonl"
    log_query(
        engine="bigquery",
        rows=3,
        latency_ms=1.234,
        models=["mart_weather_impacts", "mart_weather_impacts"],
        sql="SELECT 1",
        question="Where snow hurts reliability most",
        prebuilt_index=2,
        status="error",
        path=path,
    )
    record = json.loads(path.read_text())
    assert record["model_names"] == ["mart_weather_impacts"]
    assert record["prebuilt_index"] == 2 and record["status"] == "error"
    assert "Where snow" not in path.read_text()


def test_typo_in_first_word_names_it():
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    with pytest.raises(SqlValidationError, match=r"must start with SELECT or WITH.*'SELEC'"):
        sanitize_sql("SELEC stop_id FROM mart_access_score_by_stop", config)
    with pytest.raises(SqlValidationError, match="Only SELECT statements are allowed"):
        sanitize_sql("DELETE FROM mart_access_score_by_stop", config)


def test_generated_sql_filters_cannot_break_out_of_quotes():
    pytest.importorskip("fastapi")  # CI installs the root requirements only
    from api.models import FilterState
    from api.routers.sql import _add_filter_clauses

    sql = "SELECT route_id, stop_id, precip_bin FROM mart_reliability_by_route_day LIMIT 5"
    filters = FilterState(
        routes=["15", "15') OR TRUE --"],
        weather=["none' OR '1'='1"],
        stop_id="1' OR '1'='1",
        start_date="2026-11-01'",
        end_date="2026-11-07",
    )
    out = _add_filter_clauses(sql, filters)
    assert "route_id IN ('15')" in out
    assert "OR" not in out.upper().replace("ORDER", "")


def test_lone_semicolon_is_a_validation_error():
    config = GuardrailConfig(allowed_models={"mart_access_score_by_stop"}, engine="duckdb")
    with pytest.raises(SqlValidationError, match="No SQL provided"):
        sanitize_sql(" ; ", config)


def test_extract_from_is_not_a_table():
    sql = (
        "SELECT EXTRACT(HOUR FROM arrival_ts_mst) AS h, AVG(delay_min) AS avg_delay "
        "FROM mart_stop_visits_recent GROUP BY h"
    )
    assert referenced_tables(sql) == ["mart_stop_visits_recent"]
    config = GuardrailConfig(allowed_models={"mart_stop_visits_recent"}, engine="bigquery")
    assert "EXTRACT(HOUR FROM arrival_ts_mst)" in sanitize_sql(sql, config)
