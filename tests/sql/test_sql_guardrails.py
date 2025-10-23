from __future__ import annotations

import pytest

from whylinedenver.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql


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
