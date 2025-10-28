"""Filter utilities for SQL WHERE clause injection."""

from __future__ import annotations

import re
from typing import Any, Mapping


def add_filter_clauses(sql: str, filters: Mapping[str, Any]) -> str:
    """
    Augment SQL with WHERE clauses based on filter values.

    Only injects conditions if the relevant column exists in the SQL.
    """
    augmented_sql = sql
    lower_sql = sql.lower()

    # Date range filter
    start = filters.get("start_date")
    end = filters.get("end_date")
    if start and end and "service_date_mst" in lower_sql:
        augmented_sql = _inject_condition(
            augmented_sql,
            "service_date_mst",
            f"service_date_mst BETWEEN DATE '{start}' AND DATE '{end}'",
        )

    # Routes filter
    routes = filters.get("routes") or []
    if routes and "route_id" in lower_sql:
        formatted = ", ".join(f"'{route}'" for route in routes)
        augmented_sql = _inject_condition(augmented_sql, "route_id", f"route_id IN ({formatted})")

    # Stop ID filter
    stop_id = (filters.get("stop_id") or "").strip()
    if stop_id and "stop_id" in lower_sql:
        stop_safe = stop_id.replace("'", "''").upper()
        augmented_sql = _inject_condition(augmented_sql, "stop_id", f"stop_id = '{stop_safe}'")

    # Weather bins filter
    weather_bins = filters.get("weather") or []
    if weather_bins and "precip_bin" in lower_sql:
        formatted = ", ".join(f"'{bin}'" for bin in weather_bins)
        augmented_sql = _inject_condition(
            augmented_sql, "precip_bin", f"precip_bin IN ({formatted})"
        )

    return augmented_sql


def _inject_condition(sql: str, column: str, condition: str) -> str:
    """
    Inject a WHERE condition into SQL, handling existing WHERE, GROUP BY, ORDER BY, etc.

    If WHERE exists, appends with AND.
    If no WHERE exists, inserts before GROUP BY/ORDER BY/HAVING/LIMIT.
    """
    # Try to find existing WHERE clause
    pattern = re.compile(
        r"(WHERE\s.*?)(\bGROUP BY\b|\bORDER BY\b|\bHAVING\b|\bLIMIT\b|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    if match:
        where_clause = match.group(1)
        # Avoid duplicate conditions
        if condition in where_clause:
            return sql
        updated = where_clause.rstrip() + f"\n    AND {condition}\n"
        start, end = match.span(1)
        return sql[:start] + updated + sql[end:]

    # No WHERE clause exists - insert before GROUP BY/ORDER BY/HAVING/LIMIT
    insertion_pattern = re.compile(r"\b(GROUP BY|ORDER BY|HAVING|LIMIT)\b", re.IGNORECASE)
    insertion_match = insertion_pattern.search(sql)
    insert_pos = insertion_match.start() if insertion_match else len(sql)
    return f"{sql[:insert_pos]}\nWHERE {condition}\n{sql[insert_pos:]}"
