"""Pydantic request/response models for the WhyLine Denver API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ─── Request Models ──────────────────────────────────────────────────────────


class FilterState(BaseModel):
    """Sidebar filter values applied by the user."""

    start_date: str | None = None  # "YYYY-MM-DD"
    end_date: str | None = None  # "YYYY-MM-DD"
    routes: list[str] = Field(default_factory=list)
    stop_id: str = ""
    weather: list[str] = Field(default_factory=list)


class GenerateSqlRequest(BaseModel):
    question: str
    engine: Literal["duckdb", "bigquery"] = "duckdb"
    filters: FilterState = Field(default_factory=FilterState)


class ValidateSqlRequest(BaseModel):
    sql: str
    engine: Literal["duckdb", "bigquery"]


class RunQueryRequest(BaseModel):
    sql: str
    engine: Literal["duckdb", "bigquery"]
    question: str = ""


class MartDownloadRequest(BaseModel):
    engine: Literal["duckdb", "bigquery"]
    mart: str
    limit_rows: int = Field(default=200_000, ge=1_000, le=2_000_000)
    date_column: str | None = None
    date_start: str | None = None  # "YYYY-MM-DD"
    date_end: str | None = None  # "YYYY-MM-DD"


# ─── Response Models ─────────────────────────────────────────────────────────


class FilterOptionsResponse(BaseModel):
    routes: list[str]
    weather_bins: list[str]
    date_min: str | None
    date_max: str | None
    error: str | None = None


class ModelColumnInfo(BaseModel):
    name: str
    type: str | None = None
    description: str | None = None


class ModelInfo(BaseModel):
    name: str
    fq_name: str
    description: str | None = None
    columns: dict[str, ModelColumnInfo] = Field(default_factory=dict)


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


class GenerateSqlResponse(BaseModel):
    sql: str
    explanation: str
    cache_hit: bool = False
    error: str | None = None


class ValidateSqlResponse(BaseModel):
    valid: bool
    sanitized_sql: str | None = None
    bq_est_bytes: int | None = None
    error: str | None = None


class RunQueryResponse(BaseModel):
    rows: int
    columns: list[str]
    data: list[dict[str, Any]]
    total_rows: int
    stats: dict[str, Any]
    error: str | None = None


class FreshnessResponse(BaseModel):
    bigquery_freshness: str
    duckdb_freshness: str


class HealthResponse(BaseModel):
    status: str
    engine_default: str
