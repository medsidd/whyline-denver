"""Render dbt models to DuckDB SQL for offline tests.

Project macros are inlined into the template, except those with a DuckDB override below. Each
test still creates its own input tables, named after the `ref()`s.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined

DBT = Path(__file__).resolve().parents[2] / "dbt"
MACRO_BLOCK = re.compile(r"{%-?\s*macro\s+(\w+)\(.*?{%-?\s*endmacro\s*-?%}", re.S)

# BigQuery functions the models use, as DuckDB macros (same argument order).
DUCKDB_MACROS = """
create or replace macro farm_fingerprint(s) as hash(s);
create or replace macro timestamp_diff(a, b, unit) as date_diff(unit, b, a);
create or replace macro date_sub(d, i) as cast(d - i as date);
create or replace macro timestamp_sub(t, i) as t - i;
create or replace macro timestamp_add(t, i) as t + i;
create or replace macro div(a, b) as a // b;
create or replace macro format_date(fmt, d) as strftime(d, fmt);
create or replace macro format_datetime(fmt, d) as strftime(d, fmt);
create or replace macro logical_and(x) as bool_and(x);
create or replace macro countif(x) as count_if(x);
create or replace macro safe_divide(a, b) as case when b = 0 then null else a / b end;
"""

# Project macros whose BigQuery bodies DuckDB can't run.
JINJA_OVERRIDES = {
    "as_mst": lambda c: f"timezone('America/Denver', {c})",
    "date_mst": lambda c: f"cast(timezone('America/Denver', {c}) as date)",
    "hour_mst": lambda c: f"extract(hour from timezone('America/Denver', {c}))",
    # The BigQuery body reads INFORMATION_SCHEMA at compile time.
    "latest_extract_date": lambda rel: f"(select max(_extract_date) from {rel})",
}

REPLACEMENTS = (
    ("current_date('America/Denver')", "current_date"),
    ('current_date("America/Denver")', "current_date"),
    ("current_timestamp()", "now()"),
    (", second)", ", 'second')"),
    (", minute)", ", 'minute')"),
)


def _project_macros() -> str:
    blocks = []
    for path in sorted((DBT / "macros").rglob("*.sql")):
        for match in MACRO_BLOCK.finditer(path.read_text()):
            if match.group(1) not in JINJA_OVERRIDES:
                blocks.append(match.group(0))
    return "\n".join(blocks)


def render_model(
    relpath: str,
    *,
    incremental: bool = False,
    this: str | None = None,
    variables: dict | None = None,
    replacements: tuple[tuple[str, str], ...] = (),
) -> str:
    """Render dbt/models/<relpath> with Jinja stubs, then apply the dialect replacements."""
    variables = variables or {}
    template = _project_macros() + "\n" + (DBT / "models" / relpath).read_text()
    sql = (
        Environment(  # SQL, not HTML
            autoescape=False,  # noqa: S701
            undefined=StrictUndefined,
            extensions=["jinja2.ext.do"],
        )
        .from_string(template)
        .render(
            config=lambda **kwargs: "",
            ref=lambda name: name,
            source=lambda schema, table: table,
            var=lambda name, default=None: variables.get(name, default),
            is_incremental=lambda: incremental,
            this=this,
            **JINJA_OVERRIDES,
        )
    )
    for old, new in REPLACEMENTS + replacements:
        sql = sql.replace(old, new)
    return sql


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("set timezone = 'UTC'")
    con.execute(DUCKDB_MACROS)
    return con
