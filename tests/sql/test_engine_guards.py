"""The engines re-check visitor SQL with their own parsers; the text guard alone let these through."""

from __future__ import annotations

from types import SimpleNamespace

import duckdb
import pytest

from whyline.engines import bigquery_engine, duckdb_engine
from whyline.logs import QueryCache
from whyline.sql_guardrails import GuardrailConfig, SqlValidationError, sanitize_sql

ALLOWED = {"mart_x"}


@pytest.fixture
def warehouse(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE mart_x AS SELECT i AS a FROM range(5000) t(i)")
    con.execute("CREATE TABLE other AS SELECT 1 AS b")
    con.close()
    monkeypatch.setenv("DUCKDB_PATH", str(path))
    monkeypatch.setenv("DUCKDB_COPY_LOCAL", "0")
    # DuckDB may read inside its temp directory; the engine must not point that at tmp_path itself
    monkeypatch.setenv("DUCKDB_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(duckdb_engine, "_current_path", None)
    monkeypatch.setattr(duckdb_engine, "_thread_local", type(duckdb_engine._thread_local)())
    (tmp_path / "secret.txt").write_text("secret")
    return tmp_path


BYPASSES = [
    "SELECT * FROM mart_x a, other b",
    "SELECT * FROM /* c */ other",
    "SELECT * FROM mart_x a JOIN mart_x c ON a.a = c.a, other b",
    "SELECT a FROM mart_x UNION ALL TABLE other",
    "SELECT a FROM mart_x; SELECT b FROM other",
]


@pytest.mark.parametrize("sql", BYPASSES[:3])
def test_text_guard_alone_misses_these(sql: str):
    """If this starts failing the text guard got stricter, which is fine: update the list."""
    sanitize_sql(sql, GuardrailConfig(allowed_models=ALLOWED, engine="duckdb"))


@pytest.mark.parametrize("sql", BYPASSES)
def test_duckdb_refuses_tables_outside_the_allowlist(warehouse, sql: str):
    with pytest.raises(SqlValidationError):
        duckdb_engine.execute(sql, allowed_tables=ALLOWED, max_rows=10)


def test_duckdb_runs_allowed_joins_and_ctes(warehouse):
    """DuckDB's get_table_names failed on USING joins; the parse-tree check must not."""
    for sql in (
        "SELECT a FROM mart_x JOIN mart_x m USING (a) LIMIT 3",
        "WITH t AS (SELECT a FROM mart_x) SELECT a FROM t, unnest([1]) u(x) LIMIT 3",
    ):
        _, df = duckdb_engine.execute(sql, allowed_tables=ALLOWED, max_rows=10)
        assert len(df) == 3
    for sql in (
        "WITH t AS (SELECT 1) SELECT * FROM main.other",
        "SELECT * FROM duckdb_settings()",
        "SELECT a FROM mart_x JOIN other USING (a)",
    ):
        with pytest.raises(SqlValidationError):
            duckdb_engine.check_reads(sql, ALLOWED)


def test_duckdb_cannot_read_files(warehouse):
    secret = warehouse / "secret.txt"
    for sql in (f"SELECT * FROM read_text('{secret}')", f"SELECT * FROM '{secret}'"):
        with pytest.raises(SqlValidationError):
            duckdb_engine.execute(sql, allowed_tables=ALLOWED)
    # Internal callers pass no allowlist; the connection itself must still refuse
    for sql in (f"SELECT * FROM read_text('{secret}')", f"SELECT * FROM glob('{warehouse}/*')"):
        with pytest.raises(duckdb.Error, match="disabled"):
            duckdb_engine.execute(sql)
    with pytest.raises(duckdb.Error):
        duckdb_engine.execute("SET enable_external_access=true")


def test_duckdb_fetches_no_more_than_max_rows(warehouse):
    stats, df = duckdb_engine.execute(
        "SELECT a FROM mart_x ORDER BY a LIMIT 999999999", allowed_tables=ALLOWED, max_rows=100
    )
    assert (len(df), df["a"].iloc[-1], stats["truncated"]) == (100, 99, True)
    stats, df = duckdb_engine.execute("SELECT a FROM mart_x LIMIT 7", max_rows=100)
    assert (len(df), stats["truncated"]) == (7, False)


def _job(*tables: str, statement_type: str = "SELECT"):
    refs = [
        SimpleNamespace(project=p, dataset_id=d, table_id=t)
        for p, d, t in (name.split(".", 2) for name in tables)
    ]
    return SimpleNamespace(statement_type=statement_type, referenced_tables=refs)


@pytest.fixture
def live_tables(monkeypatch: pytest.MonkeyPatch):
    def tables():
        return frozenset({("whyline-denver", "core_denver", "dim_route")})

    tables.cache_clear = lambda: None
    monkeypatch.setattr(bigquery_engine, "_live_view_tables", tables)


def test_bigquery_allows_marts_and_live_view_tables(live_tables):
    job = _job("whyline-denver.mart_denver.mart_x", "whyline-denver.core_denver.dim_route")
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
        cache.set("duckdb", f"SELECT {i}", i)
    assert len(cache._store) == 3 and cache.get("duckdb", "SELECT 9") == 9


def test_validate_agrees_with_duckdb_run(monkeypatch: pytest.MonkeyPatch):
    """Validate used to pass DuckDB SQL that the run then refused."""
    pytest.importorskip("fastapi")
    from api.models import ValidateSqlRequest
    from api.routers import sql as sql_router

    config = GuardrailConfig(allowed_models=ALLOWED, engine="duckdb")
    monkeypatch.setattr(sql_router, "get_models", lambda: {})
    monkeypatch.setattr(sql_router, "get_guardrail_config", lambda engine: config)
    validate = sql_router.validate_sql
    ok = validate(
        ValidateSqlRequest(engine="duckdb", sql="SELECT a FROM mart_x JOIN mart_x m USING (a)")
    )
    bad = validate(ValidateSqlRequest(engine="duckdb", sql="SELECT * FROM mart_x a, other b"))
    assert (ok.valid, bad.valid) == (True, False)
