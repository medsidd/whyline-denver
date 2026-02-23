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


def _split_identifier(identifier: str) -> tuple[str | None, str | None, str | None]:
    token = identifier.strip()
    if not token:
        return (None, None, None)
    parts = [segment.strip("`").lower() for segment in token.split(".") if segment]
    if not parts:
        return (None, None, None)
    if len(parts) == 1:
        return (None, None, parts[0])
    if len(parts) == 2:
        return (None, parts[0], parts[1])
    # Normalize longer identifiers by taking the trailing project.dataset.table
    return (parts[-3], parts[-2], parts[-1])


TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN)\s+(" r"(?:`[^`]+`|[\w-]+)" r"(?:\.(?:`[^`]+`|[\w-]+)){0,2}" r")",
    re.IGNORECASE,
)

LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)", re.IGNORECASE)
CTE_PATTERN = re.compile(
    r"(?:\bWITH\b|,)\s+(`[^`]+`|[a-zA-Z_][\w-]*)\s+AS\s*\(",
    re.IGNORECASE,
)


class SqlValidationError(ValueError):
    """Raised when a generated SQL query violates guardrails."""


@dataclass(slots=True)
class GuardrailConfig:
    allowed_models: set[str]
    engine: str  # 'duckdb' | 'bigquery'
    partition_columns: Sequence[str] = ("service_date_mst",)
    enforce_limit: int = SAFE_LIMIT
    allowed_datasets: Sequence[str] | None = None
    allowed_projects: Sequence[str] | None = None


def sanitize_sql(sql: str, config: GuardrailConfig) -> str:
    parsed = _normalize(sql)
    _ensure_single_statement(parsed)
    _ensure_read_only(parsed)
    _validate_tables(
        parsed,
        config.allowed_models,
        allowed_projects=config.allowed_projects,
        allowed_datasets=config.allowed_datasets,
    )
    sanitized = _ensure_limit(parsed, config.enforce_limit)
    if config.engine == "bigquery":
        sanitized = _quote_hyphenated_tables(sanitized)
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


def _validate_tables(
    sql: str,
    allowed_models: Iterable[str],
    allowed_projects: Iterable[str] | None = None,
    allowed_datasets: Iterable[str] | None = None,
) -> None:
    allowed_base, allowed_project_set, allowed_dataset_set = _compile_allowed_sets(
        allowed_models, allowed_projects, allowed_datasets
    )
    references = _extract_referenced_identifiers(sql)
    _ensure_tables_are_allowlisted(references, allowed_base)
    _ensure_authorized_namespaces(references, allowed_project_set, allowed_dataset_set)


def _compile_allowed_sets(
    allowed_models: Iterable[str],
    explicit_projects: Iterable[str] | None,
    explicit_datasets: Iterable[str] | None,
) -> tuple[set[str], set[str], set[str]]:
    allowed_base: set[str] = set()
    derived_projects: set[str] = set()
    derived_datasets: set[str] = set()
    for model in allowed_models:
        project, dataset, table = _split_identifier(model)
        if table:
            allowed_base.add(table)
        if project:
            derived_projects.add(project)
        if dataset:
            derived_datasets.add(dataset)

    allowed_projects = {
        project.strip("`").lower() for project in explicit_projects or () if project
    }
    allowed_datasets = {
        dataset.strip("`").lower() for dataset in explicit_datasets or () if dataset
    }

    return (
        allowed_base,
        allowed_projects or derived_projects,
        allowed_datasets or derived_datasets,
    )


def _extract_referenced_identifiers(
    sql: str,
) -> list[tuple[str | None, str | None, str, str]]:
    identifiers: list[tuple[str | None, str | None, str, str]] = []
    for match in TABLE_PATTERN.finditer(sql):
        token = match.group(1).strip()
        if not token:
            continue
        project, dataset, table = _split_identifier(token)
        if table is None:
            continue
        identifiers.append((project, dataset, table, token))

    ctes = {name.strip("`").lower() for name in CTE_PATTERN.findall(sql)}
    return [ref for ref in identifiers if ref[2] not in ctes]


def _ensure_tables_are_allowlisted(
    references: Sequence[tuple[str | None, str | None, str, str]],
    allowed_tables: set[str],
) -> None:
    unauthorized = {table for _, _, table, _ in references if table not in allowed_tables}
    if unauthorized:
        raise SqlValidationError(
            f"Query references unauthorized tables: {', '.join(sorted(unauthorized))}. "
            "Only app-approved marts may be queried."
        )


def _ensure_authorized_namespaces(
    references: Sequence[tuple[str | None, str | None, str, str]],
    allowed_projects: set[str],
    allowed_datasets: set[str],
) -> None:
    if not allowed_projects and not allowed_datasets:
        return

    invalid_projects: set[str] = set()
    invalid_datasets: set[str] = set()
    for project, dataset, _table, token in references:
        if project and allowed_projects and project not in allowed_projects:
            invalid_projects.add(token)
        if dataset and allowed_datasets and dataset not in allowed_datasets:
            invalid_datasets.add(token)

    if invalid_projects:
        raise SqlValidationError(
            "Query references unauthorized project(s): "
            f"{', '.join(sorted(invalid_projects))}. Only app-approved marts may be queried."
        )
    if invalid_datasets:
        raise SqlValidationError(
            "Query references unauthorized dataset(s): "
            f"{', '.join(sorted(invalid_datasets))}. Only app-approved marts may be queried."
        )


def _ensure_limit(sql: str, max_rows: int) -> str:
    if LIMIT_PATTERN.search(sql):
        return sql
    return f"{sql}\nLIMIT {max_rows}"


def _quote_hyphenated_tables(sql: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("`") and token.endswith("`"):
            return match.group(0)
        if "-" not in token:
            return match.group(0)
        quoted = f"`{token}`"
        return match.group(0).replace(token, quoted, 1)

    return TABLE_PATTERN.sub(replacer, sql)


def _suggest_partition_filter(sql: str, partition_columns: Sequence[str]) -> None:
    upper_sql = sql.upper()
    for column in partition_columns:
        if column.upper() in upper_sql and "WHERE" not in upper_sql:
            raise SqlValidationError(
                f"The query touches `{column}` but no WHERE clause was provided. "
                "Please filter to a recent date range to keep the query efficient."
            )
