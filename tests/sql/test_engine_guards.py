"""BigQuery's dry run re-checks visitor SQL; the text guard alone let these through."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from whyline.engines import bigquery_engine
from whyline.logs import QueryCache
from whyline.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

ALLOWED = {"mart_x"}


BYPASSES = [
    "SELECT * FROM mart_x a, other b",
    "SELECT * FROM /* c */ other",
    "SELECT * FROM mart_x a JOIN mart_x c ON a.a = c.a, other b",
]


@pytest.mark.parametrize("sql", BYPASSES)
def test_text_guard_alone_misses_these(sql: str):
    """If this starts failing the text guard got stricter, which is fine: update the list."""
    sanitize_sql(sql, GuardrailConfig(allowed_models=ALLOWED))


def _job(*tables: str, statement_type: str = "SELECT", query: str = ""):
    refs = [
        SimpleNamespace(project=p, dataset_id=d, table_id=t)
        for p, d, t in (name.split(".", 2) for name in tables)
    ]
    return SimpleNamespace(statement_type=statement_type, referenced_tables=refs, query=query)


@pytest.fixture
def live_tables(monkeypatch: pytest.MonkeyPatch):
    def tables():
        return frozenset({("whyline-denver", "core_denver", "dim_route")})

    tables.cache_clear = lambda: None
    monkeypatch.setattr(bigquery_engine, "_live_view_tables", tables)


def test_bigquery_allows_marts_and_live_view_tables(live_tables):
    job = _job(
        "whyline-denver.mart_denver.mart_x",
        "whyline-denver.core_denver.dim_route",
        query="SELECT * FROM mart_x JOIN mart_vehicles_now USING (route_id)",
    )
    bigquery_engine._check_reads(job, {"mart_x", "mart_vehicles_now"})


def test_bigquery_refuses_live_view_tables_without_the_view(live_tables):
    """A comma join reached core_denver.dim_route because the live exception always applied."""
    job = _job(
        "whyline-denver.mart_denver.mart_x",
        "whyline-denver.core_denver.dim_route",
        query="SELECT * FROM mart_x, `whyline-denver.core_denver.dim_route`",
    )
    with pytest.raises(SqlValidationError):
        bigquery_engine._check_reads(job, {"mart_x", "mart_vehicles_now"})


@pytest.mark.parametrize(
    "table",
    [
        "whyline-denver.billing.gcp_billing_export_v1",
        "whyline-denver.raw_denver.raw_crashes",
        "bigquery-public-data.samples.shakespeare",
        "whyline-denver.mart_denver.mart_not_in_app",
        "whyline-denver.mart_denver.INFORMATION_SCHEMA.TABLES",
    ],
)
def test_bigquery_refuses_tables_the_dry_run_reports(live_tables, table: str):
    job = _job("whyline-denver.mart_denver.mart_x", table)
    with pytest.raises(SqlValidationError, match="unauthorized"):
        bigquery_engine._check_reads(job, {"mart_x", "mart_vehicles_now"})


def test_bigquery_refuses_scripts(live_tables):
    with pytest.raises(SqlValidationError, match="SELECT"):
        bigquery_engine._check_reads(_job(statement_type="SCRIPT"), {"mart_x"})


def test_query_cache_is_bounded():
    cache = QueryCache(max_entries=3)
    for i in range(10):
        cache.set("bigquery", f"SELECT {i}", i)
    assert len(cache._store) == 3 and cache.get("bigquery", "SELECT 9") == 9
