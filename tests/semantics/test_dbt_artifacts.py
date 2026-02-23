from __future__ import annotations

from pathlib import Path

import pytest

from whyline.semantics.dbt_artifacts import DbtArtifacts


@pytest.fixture(scope="module")
def artifacts() -> DbtArtifacts:
    target_path = Path("dbt/target")
    manifest_path = target_path / "manifest.json"
    catalog_path = target_path / "catalog.json"
    if not manifest_path.exists() or not catalog_path.exists():
        pytest.skip("dbt artifacts are missing; run dbt compile first.")
    loader = DbtArtifacts(target_path=target_path)
    loader.load_artifacts()
    return loader


def test_allowed_models_include_week4_marts(artifacts: DbtArtifacts) -> None:
    models = artifacts.allowed_models()
    expected = {
        "mart_reliability_by_route_day",
        "mart_reliability_by_stop_hour",
        "mart_crash_proximity_by_stop",
        "mart_access_score_by_stop",
        "mart_vulnerability_by_stop",
        "mart_priority_hotspots",
        "mart_weather_impacts",
    }
    assert set(models) == expected


def test_columns_and_descriptions_loaded(artifacts: DbtArtifacts) -> None:
    models = artifacts.allowed_models()
    reliability = models["mart_reliability_by_route_day"]
    assert reliability.description
    columns = reliability.columns
    assert "service_date_mst" in columns
    assert columns["service_date_mst"].type in {"DATE", "DATE32"}
    assert "route_id" in columns
    assert columns["route_id"].description
