from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("fastapi")  # CI installs the root requirements only

from fastapi import HTTPException  # noqa: E402

from api.models import MartDownloadRequest  # noqa: E402
from api.routers import downloads  # noqa: E402
from whyline.sql_guardrails import GuardrailConfig  # noqa: E402


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def execute(sql: str):
        seen.append(sql)
        return {}, pd.DataFrame({"a": [1]})

    monkeypatch.setattr(downloads.bigquery_engine, "execute", execute)
    monkeypatch.setattr(downloads, "get_models", lambda: {})
    monkeypatch.setattr(downloads, "adapt_sql_for_engine", lambda sql, *_: sql)
    monkeypatch.setattr(
        downloads, "query_cache", type("C", (), {"get": lambda *a: None, "set": lambda *a: None})()
    )
    monkeypatch.setattr(downloads, "log_query", lambda **_: None)

    config = GuardrailConfig(allowed_models=set(downloads.ALLOWED_MARTS), engine="bigquery")
    monkeypatch.setattr(downloads, "get_guardrail_config", lambda engine: config)
    return seen


def _req(**kw) -> MartDownloadRequest:
    return MartDownloadRequest(engine="bigquery", limit_rows=1000, **kw)


def test_dated_mart_keeps_newest_rows_within_dates(ran: list[str]) -> None:
    downloads.download_mart(
        _req(
            mart="mart_reliability_by_route_day",
            date_column="service_date_mst",
            date_start="2026-11-01",
            date_end="2026-11-07",
        )
    )
    assert ran[-1] == (
        "SELECT * FROM mart_reliability_by_route_day WHERE service_date_mst BETWEEN "
        "DATE '2026-11-01' AND DATE '2026-11-07' ORDER BY service_date_mst DESC LIMIT 1000"
    )


def test_dated_mart_without_dates_is_newest_first(ran: list[str]) -> None:
    downloads.download_mart(_req(mart="mart_wait_by_route_day"))
    assert ran[-1] == (
        "SELECT * FROM mart_wait_by_route_day WHERE service_date_mst IS NOT NULL "
        "ORDER BY service_date_mst DESC LIMIT 1000"
    )


def test_undated_mart_has_no_order(ran: list[str]) -> None:
    downloads.download_mart(_req(mart="mart_priority_hotspots"))
    assert ran[-1] == "SELECT * FROM mart_priority_hotspots LIMIT 1000"


@pytest.mark.parametrize(
    "kw",
    [
        dict(mart="mart_priority_hotspots", date_column="service_date_mst"),
        dict(mart="mart_reliability_by_route_day", date_column="1=1 OR route_id"),
        dict(mart="mart_reliability_by_route_day", date_column="service_date_mst", bad=True),
    ],
)
def test_bad_date_arguments_are_rejected(ran: list[str], kw: dict) -> None:
    bad = kw.pop("bad", False)
    start = "2026-11-01' OR '1'='1" if bad else "2026-11-01"
    with pytest.raises(HTTPException) as exc:
        downloads.download_mart(_req(date_start=start, date_end="2026-11-07", **kw))
    assert exc.value.status_code == 400
    assert ran == []
