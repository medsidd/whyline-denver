from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

SAFE_LIMIT = 5000
DENYLIST_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ALTER",
    "MERGE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "CALL",
    "LOAD",
    "EXPORT",
    "COPY",
}

TABLE_PATTERN = re.compile(r"\b(?:FROM|JOIN)\s+([`\w.]+)", re.IGNORECASE)
LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)", re.IGNORECASE)
CTE_PATTERN = re.compile(r"\bWITH\s+([a-zA-Z_][\w]*)\s+AS\s*\(", re.IGNORECASE)


class SqlValidationError(ValueError):
    """Raised when a generated SQL query violates guardrails."""


@dataclass(slots=True)
class GuardrailConfig:
    allowed_models: set[str]
    engine: str  # 'duckdb' | 'bigquery'
    partition_columns: Sequence[str] = ("service_date_mst",)
    enforce_limit: int = SAFE_LIMIT


def sanitize_sql(sql: str, config: GuardrailConfig) -> str:
    parsed = _normalize(sql)
    _ensure_single_statement(parsed)
    _ensure_read_only(parsed)
    _validate_tables(parsed, config.allowed_models)
    sanitized = _ensure_limit(parsed, config.enforce_limit)
    if config.engine == "bigquery":
        _suggest_partition_filter(sanitized, config.partition_columns)
    return sanitized


def _normalize(sql: str) -> str:
    if not sql or not sql.strip():
        raise SqlValidationError("No SQL provided.")
    trimmed = sql.strip()
    if trimmed.endswith(";"):
        trimmed = trimmed[:-1].strip()
    return trimmed


def _ensure_single_statement(sql: str) -> None:
    if ";" in sql:
        raise SqlValidationError(
            "Multiple SQL statements detected; only single SELECT queries are allowed."
        )


def _ensure_read_only(sql: str) -> None:
    stripped = sql.lstrip()
    upper_sql = stripped.upper()
    if upper_sql.startswith("WITH"):
        if "SELECT" not in upper_sql:
            raise SqlValidationError("CTE detected without a SELECT statement.")
    elif not upper_sql.startswith("SELECT"):
        raise SqlValidationError("Only SELECT statements are allowed.")
    for keyword in DENYLIST_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, upper_sql):
            raise SqlValidationError(f"Disallowed keyword detected: {keyword}.")


def _validate_tables(sql: str, allowed_models: Iterable[str]) -> None:
    allowed = {model.lower() for model in allowed_models}
    referenced = {match.group(1).strip("`").lower() for match in TABLE_PATTERN.finditer(sql)}
    ctes = {name.lower() for name in CTE_PATTERN.findall(sql)}
    referenced -= ctes
    unauthorized = referenced - allowed
    if unauthorized:
        raise SqlValidationError(
            f"Query references unauthorized tables: {', '.join(sorted(unauthorized))}. "
            "Only app-approved marts may be queried."
        )


def _ensure_limit(sql: str, max_rows: int) -> str:
    if LIMIT_PATTERN.search(sql):
        return sql
    return f"{sql}\nLIMIT {max_rows}"


def _suggest_partition_filter(sql: str, partition_columns: Sequence[str]) -> None:
    upper_sql = sql.upper()
    for column in partition_columns:
        if column.upper() in upper_sql and "WHERE" not in upper_sql:
            raise SqlValidationError(
                f"The query touches `{column}` but no WHERE clause was provided. "
                "Please filter to a recent date range to keep the query efficient."
            )
