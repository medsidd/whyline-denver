from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("fastapi")  # CI installs the root requirements only

from api import deps  # noqa: E402
from api.models import RunQueryRequest  # noqa: E402
from api.routers import query  # noqa: E402
from whyline.logs import QueryCache  # noqa: E402
from whyline.sql_guardrails import GuardrailConfig  # noqa: E402


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def execute(sql: str, **_):
        seen.append(sql)
        if "MAX(report_ts_utc)" in sql:
            return {}, pd.DataFrame({"t": [pd.Timestamp("2026-11-09 13:05:42", tz="UTC")]})
        return {}, pd.DataFrame({"route_id": ["15"], "n_vehicles": [10]})

    config = GuardrailConfig(allowed_models={"mart_vehicles_now", "mart_gtfs_routes"})
    monkeypatch.setattr(query.bigquery_engine, "execute", execute)
    monkeypatch.setattr(query, "get_models", lambda: {})
    monkeypatch.setattr(query, "get_guardrail_config", lambda: config)
    monkeypatch.setattr(query, "qualify_tables", lambda sql, *_: sql)
    monkeypatch.setattr(query, "_enrich_result", lambda df: df)
    monkeypatch.setattr(query, "query_cache", QueryCache(ttl_seconds=60))
    monkeypatch.setattr(query, "_live_cache", QueryCache(ttl_seconds=60))
    monkeypatch.setattr(query, "log_query", lambda **_: None)
    return seen


def test_live_result_says_when_vehicle_data_was_loaded(ran: list[str]) -> None:
    sql = "SELECT route_id, COUNT(*) AS n_vehicles FROM mart_vehicles_now GROUP BY route_id"
    out = query.run_query(RunQueryRequest(sql=sql))
    assert out.error is None and out.is_live
    assert out.live_loaded_at == "2026-11-09 13:05 UTC"
    query.run_query(RunQueryRequest(sql=sql + " "))
    assert sum("MAX(report_ts_utc)" in s for s in ran) == 1  # cached for a minute


def test_nightly_result_is_not_live(ran: list[str]) -> None:
    out = query.run_query(RunQueryRequest(sql="SELECT route_id FROM mart_gtfs_routes"))
    assert not out.is_live and out.live_loaded_at is None
    assert not any("MAX(report_ts_utc)" in s for s in ran)


def test_live_views_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    from whyline.semantics.dbt_artifacts import ModelInfo

    models = {
        name: ModelInfo(name=name, fq_name=name, description=None)
        for name in ("mart_vehicles_now", "mart_gtfs_routes")
    }
    monkeypatch.setattr(deps, "_load_models", lambda: models)
    assert deps.get_guardrail_config().allowed_models == set(models)
