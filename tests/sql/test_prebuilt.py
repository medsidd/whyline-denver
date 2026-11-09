from __future__ import annotations

import pytest

from whyline.prebuilt import PREBUILT, build_prebuilt_sql, clean_filters, is_live
from whyline.sql_guardrails import GuardrailConfig, referenced_tables, sanitize_sql

ALL = {
    "start_date": "2026-11-01",
    "end_date": "2026-11-07",
    "routes": ["15", "0L"],
    "stop_id": "12084",
    "weather": ["none"],
}


def _config(sql: str) -> GuardrailConfig:
    return GuardrailConfig(allowed_models=set(referenced_tables(sql)), engine="bigquery")


@pytest.mark.parametrize("index", range(len(PREBUILT)))
@pytest.mark.parametrize("filters", [None, {}, ALL])
def test_every_question_builds_and_passes_guardrails(index: int, filters) -> None:
    built = build_prebuilt_sql(index, filters)
    assert "{" not in built.sql
    assert sanitize_sql(built.sql, _config(built.sql)) == built.sql
    assert set(built.applied) <= PREBUILT[index].supports


def test_applied_and_skipped_match_support_table() -> None:
    expected = {
        0: ["dates", "routes", "weather"],
        1: ["stop"],
        2: ["routes"],
        3: ["stop"],
        4: ["routes"],
        5: ["dates", "routes"],
        6: ["dates", "routes"],
        7: ["routes"],
        8: ["routes"],
    }
    for index, applied in expected.items():
        built = build_prebuilt_sql(index, ALL)
        assert built.applied == applied
        assert built.skipped == [
            n for n in ("dates", "routes", "stop", "weather") if n not in applied
        ]


def test_unset_filters_are_not_reported_as_skipped() -> None:
    built = build_prebuilt_sql(1, {"routes": [], "stop_id": ""})
    assert built.applied == [] and built.skipped == []
    assert "WHERE" not in built.sql


def test_user_dates_replace_the_default_window() -> None:
    default = build_prebuilt_sql(6, None).sql
    assert "INTERVAL 7 DAY" in default and "CURRENT_DATE" in default

    sql = build_prebuilt_sql(6, ALL).sql
    assert "CURRENT_DATE" not in sql
    assert sql.count("service_date_mst") == 1
    assert "service_date_mst BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'" in sql


def test_filters_use_the_table_alias() -> None:
    sql = build_prebuilt_sql(7, ALL).sql
    assert "s.route_id IN ('15', '0L')" in sql


def test_filters_without_existing_where_add_one() -> None:
    sql = build_prebuilt_sql(1, ALL).sql
    assert "FROM mart_crash_proximity_by_stop\nWHERE stop_id = '12084'\nORDER BY" in sql


@pytest.mark.parametrize(
    "filters, rejected",
    [
        ({"routes": ["15') OR TRUE --"]}, "routes"),
        ({"weather": ["none'"]}, "weather"),
        ({"stop_id": "1' OR '1'='1"}, "stop"),
        ({"start_date": "2026-11-01' OR TRUE", "end_date": "2026-11-07"}, "dates"),
        ({"start_date": "2026-11-08", "end_date": "2026-11-01"}, "dates"),
    ],
)
def test_unsafe_values_are_rejected(filters, rejected: str) -> None:
    clean = clean_filters(filters)
    assert clean.rejected == (rejected,)
    built = build_prebuilt_sql(0, filters)
    assert (
        "'" not in built.sql.split("FROM", 1)[1].replace("''", "") or rejected not in built.applied
    )
    assert "OR TRUE" not in built.sql and "'1'='1" not in built.sql
    assert rejected in built.skipped


def test_valid_values_survive_next_to_invalid_ones() -> None:
    clean = clean_filters({"routes": ["15", "bad'"], "stop_id": " 12084 "})
    assert clean.routes == ("15",) and clean.stop_id == "12084" and clean.rejected == ("routes",)


def test_partly_invalid_filter_is_applied_and_skipped() -> None:
    built = build_prebuilt_sql(0, {"routes": ["15", "bad route"]})
    assert built.applied == ["routes"] and built.skipped == ["routes"]
    assert "route_id IN ('15')" in built.sql


def test_only_the_live_question_reads_live_views() -> None:
    assert [i for i in range(len(PREBUILT)) if is_live(build_prebuilt_sql(i).sql)] == [8]
    assert is_live("SELECT * FROM `whyline-denver.mart_denver.mart_stop_visits_recent` LIMIT 5")
    assert not is_live("WITH mart_vehicles_now AS (SELECT 1 AS x) SELECT * FROM mart_vehicles_now")
