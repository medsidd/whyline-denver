"""Shared FastAPI dependencies — loaded once at process start."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends

# Ensure src/ is on the path when running from the project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from whyline.config import settings
from whyline.llm import build_schema_brief
from whyline.semantics.dbt_artifacts import DbtArtifacts
from whyline.semantics.dbt_artifacts import ModelInfo as WhylineModelInfo
from whyline.sql_guardrails import GuardrailConfig


@lru_cache(maxsize=1)
def _load_models() -> dict[str, WhylineModelInfo]:
    """Load allowed dbt models exactly once per process."""
    artifacts = DbtArtifacts()
    return artifacts.allowed_models()


@lru_cache(maxsize=1)
def _build_schema_brief_cached() -> str:
    """Build schema brief exactly once per process."""
    return build_schema_brief(_load_models())


_stop_lookup_df: pd.DataFrame | None = None
_route_lookup_df: pd.DataFrame | None = None


def _mart_table(name: str) -> pd.DataFrame | None:
    """A small mart read whole from BigQuery, or None if it can't be read now."""
    from whyline.engines import bigquery_engine

    table = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{name}`"
    columns = {
        "mart_gtfs_stops": "stop_id, stop_name, lat, lon",
        "mart_gtfs_routes": "route_id, route_name, route_long_name, route_type",
    }[name]
    try:
        _, df = bigquery_engine.execute(f"SELECT {columns} FROM {table}")
    except Exception:  # noqa: BLE001 - results are shown without the extra columns
        return None
    return df if not df.empty else None


def get_stop_lookup() -> pd.DataFrame | None:
    """Stop names and positions (mart_gtfs_stops, about 8,300 rows), cached once read."""
    global _stop_lookup_df
    if _stop_lookup_df is None:
        df = _mart_table("mart_gtfs_stops")
        if df is not None:
            df["stop_id"] = df["stop_id"].astype(str)
        _stop_lookup_df = df
    return _stop_lookup_df


def get_route_lookup() -> pd.DataFrame | None:
    """Route names (mart_gtfs_routes), cached once read."""
    global _route_lookup_df
    if _route_lookup_df is None:
        df = _mart_table("mart_gtfs_routes")
        if df is not None:
            df["route_id"] = df["route_id"].astype(str)
        _route_lookup_df = df
    return _route_lookup_df


def get_models() -> dict[str, WhylineModelInfo]:
    return _load_models()


def get_schema_brief() -> str:
    return _build_schema_brief_cached()


def get_allowlist() -> set[str]:
    return set(_load_models().keys())


def get_guardrail_config() -> GuardrailConfig:
    """Allowed marts, plus the projects and datasets they live in."""
    models = _load_models()
    allowed_projects: set[str] = set()
    allowed_datasets: set[str] = set()
    for info in models.values():
        parts = [seg.strip("`") for seg in info.fq_name.split(".") if seg]
        if len(parts) >= 3:
            allowed_projects.add(parts[-3])
        if len(parts) >= 2:
            allowed_datasets.add(parts[-2])
    if not allowed_projects and settings.GCP_PROJECT_ID:
        allowed_projects.add(settings.GCP_PROJECT_ID)
    if not allowed_datasets and settings.BQ_DATASET_MART:
        allowed_datasets.add(settings.BQ_DATASET_MART)
    return GuardrailConfig(
        allowed_models=set(models),
        allowed_projects=allowed_projects,
        allowed_datasets=allowed_datasets,
    )


# FastAPI Depends wrappers
ModelsDepend = Annotated[dict[str, WhylineModelInfo], Depends(get_models)]
SchemaBriefDepend = Annotated[str, Depends(get_schema_brief)]
AllowlistDepend = Annotated[set[str], Depends(get_allowlist)]
