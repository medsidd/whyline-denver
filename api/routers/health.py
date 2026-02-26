"""Health and freshness endpoints."""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.models import FreshnessResponse, HealthResponse
from whyline.config import settings
from whyline.sync.state_store import load_sync_state

router = APIRouter()


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "Unavailable"
    try:
        from datetime import datetime

        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(ts)
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        try:
            parsed = datetime.utcfromtimestamp(float(ts))
            return parsed.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            return ts


@lru_cache(maxsize=1)
def _cached_sync_state() -> dict | None:
    """Load sync_state once (callers invalidate by recreating the cache or reloading)."""
    return load_sync_state()


def _read_duckdb_freshness() -> str:
    payload = load_sync_state()
    if not payload:
        return "Unavailable"
    ts = payload.get("duckdb_synced_at_utc") or payload.get("refreshed_at_utc")
    if ts:
        return _format_ts(ts)
    marts = payload.get("marts")
    if isinstance(marts, dict) and marts:
        latest = max(marts.values())
        return f"Latest run_date {latest}"
    return "Awaiting first DuckDB sync"


def _read_bigquery_freshness() -> str:
    payload = load_sync_state()
    if payload:
        ts = payload.get("bigquery_updated_at_utc")
        if ts:
            return _format_ts(ts)
    try:
        dbt_path = ROOT / "dbt" / "target" / "run_results.json"
        if dbt_path.exists():
            dbt_payload = json.loads(dbt_path.read_text(encoding="utf-8"))
            generated_at = dbt_payload.get("metadata", {}).get("generated_at")
            if generated_at:
                return _format_ts(generated_at)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return "Unavailable"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        engine_default=os.getenv(
            "ENGINE", settings.ENGINE if hasattr(settings, "ENGINE") else "duckdb"
        ),
    )


@router.get("/freshness", response_model=FreshnessResponse)
def freshness() -> FreshnessResponse:
    return FreshnessResponse(
        bigquery_freshness=_read_bigquery_freshness(),
        duckdb_freshness=_read_duckdb_freshness(),
    )
