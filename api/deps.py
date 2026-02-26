"""Shared FastAPI dependencies — loaded once at process start."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
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


@lru_cache(maxsize=1)
def get_stop_lookup() -> pd.DataFrame | None:
    """Load stop geometry from mart_gtfs_stops in DuckDB, falling back to local GTFS zip."""
    import zipfile

    import pandas as pd

    # Primary: query DuckDB warehouse (works in Cloud Run where GTFS zip is not bundled)
    try:
        from whyline.engines import duckdb_engine

        _, df = duckdb_engine.execute("SELECT stop_id, stop_name, lat, lon FROM mart_gtfs_stops")
        if not df.empty:
            df["stop_id"] = df["stop_id"].astype(str)
            return df
    except Exception:
        pass

    # Fallback: read from local GTFS zip (local dev without warehouse)
    gtfs_zip = ROOT / "data" / "raw" / "rtd_gtfs" / "current" / "gtfs.zip"
    try:
        with zipfile.ZipFile(gtfs_zip) as zf:
            with zf.open("stops.txt") as f:
                df = pd.read_csv(
                    f,
                    dtype={"stop_id": str},
                    usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"],
                )
        return df.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_route_lookup() -> pd.DataFrame | None:
    """Load route metadata from mart_gtfs_routes in DuckDB."""
    try:
        from whyline.engines import duckdb_engine

        _, df = duckdb_engine.execute(
            "SELECT route_id, route_name, route_long_name, route_type FROM mart_gtfs_routes"
        )
        if not df.empty:
            df["route_id"] = df["route_id"].astype(str)
            return df
    except Exception:
        pass
    return None


def get_models() -> dict[str, WhylineModelInfo]:
    return _load_models()


def get_schema_brief() -> str:
    return _build_schema_brief_cached()


def get_allowlist() -> set[str]:
    return set(_load_models().keys())


def get_guardrail_config(engine: str) -> GuardrailConfig:
    """Build guardrail config, adding BQ project/dataset constraints when needed."""
    models = _load_models()
    allowlist = set(models.keys())

    extra: dict[str, set[str]] = {}
    if engine == "bigquery":
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
        extra["allowed_projects"] = allowed_projects
        extra["allowed_datasets"] = allowed_datasets

    return GuardrailConfig(allowed_models=allowlist, engine=engine, **extra)


# FastAPI Depends wrappers
ModelsDepend = Annotated[dict[str, WhylineModelInfo], Depends(get_models)]
SchemaBriefDepend = Annotated[str, Depends(get_schema_brief)]
AllowlistDepend = Annotated[set[str], Depends(get_allowlist)]
