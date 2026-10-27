"""Exercise the Type 2 dimension macro offline against a small extract history."""

from datetime import date
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined

MACROS = Path(__file__).resolve().parents[2] / "dbt/macros/extracts.sql"


def render_scd2() -> str:
    env = Environment(autoescape=False, undefined=StrictUndefined)  # noqa: S701 - SQL, not HTML
    sql = env.from_string(
        MACROS.read_text()
        + "{{ scd2_from_extracts('extracts', 'stop_id', ['stop_name'], 'stop_key') }}"
    ).render()
    # Only the hashing and date arithmetic differ for this offline execution.
    return (
        sql.replace("farm_fingerprint(", "hash(")
        .replace("to_json_string(struct(", "md5(concat_ws('|', ")
        .replace("date_sub(next_valid_from, interval 1 day)", "next_valid_from - 1")
    )


def test_versions_follow_attribute_changes_and_retirement():
    with duckdb.connect() as con:
        con.execute(
            """
            CREATE TABLE extracts AS SELECT * FROM (VALUES
                (DATE '2026-01-01', 'A', 'Alpha'),
                (DATE '2026-01-02', 'A', 'Alpha'),
                (DATE '2026-01-03', 'A', 'Alpha St'),
                (DATE '2026-01-04', 'A', 'Alpha'),
                (DATE '2026-01-01', 'B', 'Beta'),
                (DATE '2026-01-02', 'B', 'Beta'),
                (DATE '2026-01-03', 'C', 'Gamma'),
                (DATE '2026-01-04', 'C', 'Gamma')
            ) e(_extract_date, stop_id, stop_name)
            """
        )
        rows = con.execute(
            "SELECT stop_id, stop_name, valid_from, valid_to, is_current, is_latest_version "
            "FROM (" + render_scd2() + ") ORDER BY stop_id, valid_from"
        ).fetchall()

    open_end = date(9999, 12, 31)
    backdated = date(1900, 1, 1)
    assert rows == [
        # A change back to an earlier value is a new version, not a reopened old one.
        ("A", "Alpha", backdated, date(2026, 1, 2), False, False),
        ("A", "Alpha St", date(2026, 1, 3), date(2026, 1, 3), False, False),
        ("A", "Alpha", date(2026, 1, 4), open_end, True, True),
        # Missing from the latest extract: closed on its last extract, still the latest version.
        ("B", "Beta", backdated, date(2026, 1, 2), False, True),
        ("C", "Gamma", backdated, open_end, True, True),
    ]
