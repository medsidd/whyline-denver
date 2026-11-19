from __future__ import annotations

from whyline.llm import qualify_tables
from whyline.semantics.dbt_artifacts import ModelInfo


def test_qualify_tables_qualifies_models_with_hyphenated_project() -> None:
    sql = "SELECT * FROM mart_reliability_by_route_day"
    models = {
        "mart_reliability_by_route_day": ModelInfo(
            name="mart_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.mart_reliability_by_route_day",
            description=None,
        )
    }
    result = qualify_tables(sql, models)
    assert "FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`" in result


def test_qualify_tables_leaves_already_qualified_tables_alone() -> None:
    sql = "SELECT * FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`"
    models = {
        "mart_reliability_by_route_day": ModelInfo(
            name="mart_reliability_by_route_day",
            fq_name="whyline-denver.mart_denver.mart_reliability_by_route_day",
            description=None,
        )
    }
    result = qualify_tables(sql, models)
    assert result == sql


def test_prompt_asks_for_exactly_the_users_dates() -> None:
    from whyline.llm import build_prompt

    with_dates = build_prompt("q", {"start_date": "2026-11-01", "end_date": "2026-11-07"}, "")
    assert "service_date_mst BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'" in with_dates
    assert "no other date window" in with_dates and "30-90 days" not in with_dates

    without = build_prompt("q", {"start_date": None, "end_date": None}, "")
    assert "30-90 days" in without and "no other date window" not in without


def test_prompt_points_live_questions_at_the_live_views() -> None:
    from whyline.llm import build_prompt

    prompt = build_prompt("What routes are running right now?", {}, "")
    assert "mart_vehicles_now" in prompt and "mart_stop_visits_recent" in prompt
    assert "15 to 30 minutes" in prompt


def test_bigquery_qualifier_leaves_extract_from_alone() -> None:
    from whyline.llm import qualify_tables
    from whyline.semantics.dbt_artifacts import ModelInfo

    models = {
        "mart_stop_visits_recent": ModelInfo(
            name="mart_stop_visits_recent", fq_name="x", description=None
        )
    }
    out = qualify_tables(
        "SELECT EXTRACT(HOUR FROM arrival_ts_mst) h FROM mart_stop_visits_recent", models
    )
    assert "EXTRACT(HOUR FROM arrival_ts_mst)" in out
    assert out.count("mart_denver") == 1


def test_prompt_gives_todays_denver_date(monkeypatch) -> None:
    """Asked about "yesterday", the model guessed the last day of the user's dates."""
    from datetime import date

    from whyline import llm

    monkeypatch.setattr(llm, "denver_today", lambda: date(2026, 11, 19))
    assert "Today in Denver is 2026-11-19" in llm.build_prompt("q", {}, "")
