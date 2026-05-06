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


def test_prompt_models_are_new_dimensional_set(artifacts: DbtArtifacts) -> None:
    models = artifacts.prompt_models()
    expected = {
        "dim_stop",
        "dim_route",
        "dim_date",
        "dim_weather",
        "agg_reliability_by_route_day",
        "agg_reliability_by_stop_hour",
        "agg_weather_impacts_by_route",
        "mart_stop_safety",
        "mart_stop_access",
        "mart_stop_equity",
        "mart_stop_priority",
    }
    assert set(models) == expected


def test_sql_models_include_deprecated(artifacts: DbtArtifacts) -> None:
    """sql_models() must include deprecated compat views so old cached SQL validates."""
    models = artifacts.sql_models()
    deprecated = {
        "mart_reliability_by_route_day",
        "mart_reliability_by_stop_hour",
        "mart_crash_proximity_by_stop",
        "mart_access_score_by_stop",
        "mart_vulnerability_by_stop",
        "mart_priority_hotspots",
        "mart_weather_impacts",
        "mart_gtfs_stops",
        "mart_gtfs_routes",
    }
    assert deprecated.issubset(set(models))


def test_columns_and_descriptions_loaded(artifacts: DbtArtifacts) -> None:
    models = artifacts.prompt_models()
    reliability = models["agg_reliability_by_route_day"]
    assert reliability.description
    columns = reliability.columns
    assert "service_date_mst" in columns
    assert columns["service_date_mst"].type in {"DATE", "DATE32"}
    assert "route_id" in columns
    assert columns["route_id"].description


def test_model_layer_populated(artifacts: DbtArtifacts) -> None:
    models = artifacts.prompt_models()
    assert models["dim_stop"].layer == "dim"
    assert models["agg_reliability_by_route_day"].layer == "agg"
    assert models["mart_stop_priority"].layer == "mart"
