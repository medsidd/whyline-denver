"""Health and freshness endpoints."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.models import FreshnessResponse, HealthResponse
from whyline.sync.state_store import load_sync_state

router = APIRouter()

_DENVER_TZ = ZoneInfo("America/Denver")


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "Unavailable"
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        denver = parsed.astimezone(_DENVER_TZ)
        return denver.strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, TypeError):
        try:
            parsed = datetime.utcfromtimestamp(float(ts)).replace(tzinfo=UTC)
            denver = parsed.astimezone(_DENVER_TZ)
            return denver.strftime("%Y-%m-%d %H:%M %Z")
        except (ValueError, TypeError):
            return ts


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
    return HealthResponse(status="ok")


@router.get("/freshness", response_model=FreshnessResponse)
def freshness() -> FreshnessResponse:
    return FreshnessResponse(bigquery_freshness=_read_bigquery_freshness())
