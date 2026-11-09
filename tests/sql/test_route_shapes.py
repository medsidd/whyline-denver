from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("fastapi")  # CI installs the root requirements only

from api.routers import filters  # noqa: E402
from whyline.logs import QueryCache  # noqa: E402

LINE = '{"type":"LineString","coordinates":[[-104.99,39.74],[-104.98,39.75]]}'


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def execute(sql: str):
        seen.append(sql)
        return {}, pd.DataFrame(
            {"route_id": ["15", "15", "0"], "direction_id": [0, 1, 0], "geojson": [LINE] * 3}
        )

    monkeypatch.setattr(filters.bigquery_engine, "execute", execute)
    monkeypatch.setattr(filters, "_shapes_cache", QueryCache(ttl_seconds=60))
    monkeypatch.setattr(filters, "_shapes_failures", QueryCache(ttl_seconds=60))
    return seen


def test_returns_both_directions_in_request_order_and_caches(engine: list[str]) -> None:
    out = filters.get_route_shapes("0,15,0")
    assert [(s.route_id, s.direction_id) for s in out] == [("0", 0), ("15", 0), ("15", 1)]
    assert out[0].path == [[-104.99, 39.74], [-104.98, 39.75]]
    filters.get_route_shapes("15")
    assert len(engine) == 1  # one query per process until the cache expires
    assert "mart_route_shapes" in engine[0]


def test_multilinestrings_become_one_path_per_part(monkeypatch: pytest.MonkeyPatch) -> None:
    multi = '{"type":"MultiLineString","coordinates":[[[0,0],[1,1]],[[2,2],[3,3]],[[4,4]]]}'
    monkeypatch.setattr(
        filters.bigquery_engine,
        "execute",
        lambda sql: (
            {},
            pd.DataFrame({"route_id": ["A"], "direction_id": [0], "geojson": [multi]}),
        ),
    )
    monkeypatch.setattr(filters, "_shapes_cache", QueryCache(ttl_seconds=60))
    monkeypatch.setattr(filters, "_shapes_failures", QueryCache(ttl_seconds=60))
    paths = [s.path for s in filters.get_route_shapes("A")]
    assert paths == [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]  # the one-point part is dropped


def test_skips_invalid_and_unknown_ids_and_caps_the_count(engine: list[str]) -> None:
    assert filters.get_route_shapes("15') OR TRUE --,nope,") == []
    many = ",".join(["0"] + [f"R{i}" for i in range(20)] + ["15"])
    assert {s.route_id for s in filters.get_route_shapes(many)} == {"0"}  # 15 is past the cap


def test_points_and_collections_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        '{"type":"Point","coordinates":[1,2]}',
        '{"type":"GeometryCollection","geometries":[]}',
        LINE,
    ]
    monkeypatch.setattr(
        filters.bigquery_engine,
        "execute",
        lambda sql: (
            {},
            pd.DataFrame({"route_id": ["P", "G", "L"], "direction_id": [0, 0, 0], "geojson": rows}),
        ),
    )
    monkeypatch.setattr(filters, "_shapes_cache", QueryCache(ttl_seconds=60))
    monkeypatch.setattr(filters, "_shapes_failures", QueryCache(ttl_seconds=60))
    assert [s.route_id for s in filters.get_route_shapes("P,G,L")] == ["L"]


def test_missing_table_gives_no_shapes_and_is_retried_after_a_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def boom(sql: str):
        calls.append(sql)
        raise RuntimeError("Not found: Table mart_route_shapes")

    monkeypatch.setattr(filters.bigquery_engine, "execute", boom)
    monkeypatch.setattr(filters, "_shapes_cache", QueryCache(ttl_seconds=60))
    failures = QueryCache(ttl_seconds=60)
    monkeypatch.setattr(filters, "_shapes_failures", failures)
    assert filters.get_route_shapes("15") == []
    assert filters.get_route_shapes("15") == []
    assert len(calls) == 1  # the failure is remembered, not retried on every map
    monkeypatch.setattr(filters, "_shapes_failures", QueryCache(ttl_seconds=60))
    assert filters.get_route_shapes("15") == []
    assert len(calls) == 2
