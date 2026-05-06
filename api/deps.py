"""Shared FastAPI dependencies — loaded once at process start."""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from whyline.config import settings
from whyline.llm import build_schema_brief
from whyline.semantics.dbt_artifacts import DbtArtifacts
from whyline.semantics.dbt_artifacts import ModelInfo as WhylineModelInfo
from whyline.sql_guardrails import GuardrailConfig

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_sql_models() -> dict[str, WhylineModelInfo]:
    """Load SQL-guardrail models (allow_sql=True, includes deprecated) once per process."""
    artifacts = DbtArtifacts()
    if os.getenv("STRICT_MODEL_VALIDATION"):
        artifacts.validate_registry_completeness()
    return artifacts.sql_models()


@lru_cache(maxsize=1)
def _load_prompt_models() -> dict[str, WhylineModelInfo]:
    """Load LLM-prompt models (allow_prompt=True, no deprecated) once per process."""
    return DbtArtifacts().prompt_models()


@lru_cache(maxsize=1)
def _build_schema_brief_cached() -> str:
    """Build schema brief exactly once per process from prompt models."""
    return build_schema_brief(_load_prompt_models())


_stop_lookup_df: pd.DataFrame | None = None
_route_lookup_df: pd.DataFrame | None = None


def get_stop_lookup() -> pd.DataFrame | None:
    """Load stop attributes from dim_stop in DuckDB, falling back to local GTFS zip.

    Caches on first successful load; retries on every call if the previous
    attempt returned None (avoids permanently caching a transient failure).
    """
    global _stop_lookup_df
    if _stop_lookup_df is not None:
        return _stop_lookup_df

    import zipfile

    # Primary: query DuckDB warehouse
    try:
        from whyline.engines import duckdb_engine

        _, df = duckdb_engine.execute("SELECT stop_id, stop_name, lat, lon FROM dim_stop")
        if not df.empty:
            df["stop_id"] = df["stop_id"].astype(str)
            _stop_lookup_df = df
            return _stop_lookup_df
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
        result = df.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})
        _stop_lookup_df = result
        return _stop_lookup_df
    except Exception:
        return None


def get_route_lookup() -> pd.DataFrame | None:
    """Load route metadata from dim_route in DuckDB.

    Caches on first successful load; retries on every call if the previous
    attempt returned None (avoids permanently caching a transient failure).
    """
    global _route_lookup_df
    if _route_lookup_df is not None:
        return _route_lookup_df

    try:
        from whyline.engines import duckdb_engine

        _, df = duckdb_engine.execute(
            "SELECT route_id, route_name, route_long_name, route_type FROM dim_route"
        )
        if not df.empty:
            df["route_id"] = df["route_id"].astype(str)
            _route_lookup_df = df
            return _route_lookup_df
    except Exception:
        pass
    return None


def get_models() -> dict[str, WhylineModelInfo]:
    """SQL-guardrail models — use for guardrails and BQ table qualification."""
    return _load_sql_models()


def get_prompt_models() -> dict[str, WhylineModelInfo]:
    """Prompt-set models — use for /api/models (self-serve, no deprecated)."""
    return _load_prompt_models()


def get_schema_brief() -> str:
    return _build_schema_brief_cached()


def get_allowlist() -> set[str]:
    return set(_load_sql_models().keys())


def get_guardrail_config(engine: str) -> GuardrailConfig:
    """Build guardrail config, adding BQ project/dataset constraints when needed."""
    models = _load_sql_models()
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
        if not allowed_datasets:
            # Multi-dataset: accept both stg and mart datasets
            for ds in filter(None, [settings.BQ_DATASET_STG, settings.BQ_DATASET_MART]):
                allowed_datasets.add(ds)
        extra["allowed_projects"] = allowed_projects
        extra["allowed_datasets"] = allowed_datasets

    return GuardrailConfig(allowed_models=allowlist, engine=engine, **extra)


# FastAPI Depends wrappers
ModelsDepend = Annotated[dict[str, WhylineModelInfo], Depends(get_models)]
SchemaBriefDepend = Annotated[str, Depends(get_schema_brief)]
AllowlistDepend = Annotated[set[str], Depends(get_allowlist)]
