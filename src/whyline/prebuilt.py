"""Ready-made questions and the filter-rail values they accept.

Each question is a SQL template. `build_prebuilt_sql` fills in the user's dates in place of the
default window, adds route, stop and weather predicates the question supports, and reports which
filters it applied and which it skipped. Filter values are validated here before they reach SQL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

ROUTE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,16}")
STOP_PATTERN = re.compile(r"[A-Za-z0-9]{1,16}")
WEATHER_PATTERN = ROUTE_PATTERN

# Filter names as the API reports them, in the order the dashboard lists them.
FILTER_NAMES = ("dates", "routes", "stop", "weather")


@dataclass(frozen=True)
class CleanFilters:
    """Filter-rail values that are safe to put in SQL. `rejected` names filters dropped as invalid."""

    start_date: date | None = None
    end_date: date | None = None
    routes: tuple[str, ...] = ()
    stop_id: str = ""
    weather: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()

    def is_set(self, name: str) -> bool:
        return {
            "dates": self.start_date is not None,
            "routes": bool(self.routes),
            "stop": bool(self.stop_id),
            "weather": bool(self.weather),
        }[name]


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def clean_filters(filters: Mapping[str, Any] | None) -> CleanFilters:
    """Validate FilterState values. Invalid values are dropped and their filter named in `rejected`."""
    filters = filters or {}
    rejected: list[str] = []

    raw_start, raw_end = filters.get("start_date"), filters.get("end_date")
    start, end = _parse_date(raw_start), _parse_date(raw_end)
    if start is None or end is None or start > end:
        if raw_start or raw_end:
            rejected.append("dates")
        start = end = None

    def keep(values: Any, pattern: re.Pattern[str], name: str) -> tuple[str, ...]:
        values = [str(v).strip() for v in values or [] if str(v).strip()]
        good = tuple(dict.fromkeys(v for v in values if pattern.fullmatch(v)))
        if len(good) < len(values):
            rejected.append(name)
        return good

    routes = keep(filters.get("routes"), ROUTE_PATTERN, "routes")
    weather = keep(filters.get("weather"), WEATHER_PATTERN, "weather")

    stop_id = str(filters.get("stop_id") or "").strip().upper()
    if stop_id and not STOP_PATTERN.fullmatch(stop_id):
        rejected.append("stop")
        stop_id = ""

    return CleanFilters(start, end, routes, stop_id, weather, tuple(rejected))


def _in_list(values: tuple[str, ...]) -> str:
    # Values matched ROUTE_PATTERN, so they hold no quotes.
    return ", ".join(f"'{v}'" for v in values)


def date_predicate(f: CleanFilters, column: str = "service_date_mst") -> str:
    return f"{column} BETWEEN DATE '{f.start_date.isoformat()}' AND DATE '{f.end_date.isoformat()}'"


def route_predicate(f: CleanFilters, column: str = "route_id") -> str:
    return f"{column} IN ({_in_list(f.routes)})"


def stop_predicate(f: CleanFilters, column: str = "stop_id") -> str:
    return f"{column} = '{f.stop_id}'"


def weather_predicate(f: CleanFilters, column: str = "precip_bin") -> str:
    return f"{column} IN ({_in_list(f.weather)})"


@dataclass(frozen=True)
class Prebuilt:
    """A ready-made question.

    `sql` holds `{dates}` where the date predicate goes (when `default_window` is set) and
    `{filters}` where extra predicates go: rendered as `AND …` lines after an existing WHERE,
    or as a new WHERE clause when the template has none.
    """

    label: str
    explanation: str
    sql: str
    supports: frozenset[str]
    default_window: str = ""
    alias: str = ""


PREBUILT: list[Prebuilt] = [
    Prebuilt(
        label="Worst 10 routes by on-time share",
        explanation=(
            "Averages each route's daily on-time share over the chosen dates and lists the 10 "
            "lowest. A visit is on time from less than 1 minute early to 5 minutes late, at every "
            "stop; only days measured that way (from October 29, 2026) count, and each day counts "
            "the same however many buses ran."
        ),
        sql=(
            "SELECT route_id, AVG(pct_on_time) AS avg_pct_on_time\n"
            "FROM mart_reliability_by_route_day\n"
            "WHERE {dates}\n"
            "  AND data_version IS NOT NULL{filters}\n"
            "GROUP BY route_id\n"
            "ORDER BY avg_pct_on_time ASC\n"
            "LIMIT 10"
        ),
        supports=frozenset({"dates", "routes", "weather"}),
        default_window="service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)",
    ),
    Prebuilt(
        label="Stops with highest crash exposure",
        explanation=(
            "Lists the 20 stops with the most traffic crashes within 250 m over the latest year of "
            "Denver's crash records, with the stop name and location."
        ),
        sql=(
            "SELECT stop_id, stop_name, crash_250m_cnt, lat, lon\n"
            "FROM mart_crash_proximity_by_stop{filters}\n"
            "ORDER BY crash_250m_cnt DESC\n"
            "LIMIT 20"
        ),
        supports=frozenset({"stop"}),
    ),
    Prebuilt(
        label="Where snow hurts reliability most",
        explanation=(
            "For each route, compares the on-time share on snow days with other days over the last "
            "year and lists the 10 with the biggest drop. Routes need at least 3 snow days, so this "
            "question keeps its one-year window rather than your dates. It compares within one "
            "measuring method at a time, so a route can appear twice."
        ),
        sql=(
            "SELECT route_id,\n"
            "  COALESCE(data_version, 'sampled') AS method,\n"
            "  AVG(CASE WHEN snow_day THEN pct_on_time END)\n"
            "    - AVG(CASE WHEN NOT snow_day THEN pct_on_time END) AS delta_pct_on_time,\n"
            "  AVG(CASE WHEN snow_day THEN pct_on_time END) AS pct_on_time_snow_days,\n"
            "  AVG(CASE WHEN NOT snow_day THEN pct_on_time END) AS pct_on_time_other_days,\n"
            "  SUM(CASE WHEN snow_day THEN 1 ELSE 0 END) AS n_snow_days\n"
            "FROM mart_reliability_by_route_day\n"
            "WHERE service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 365 DAY){filters}\n"
            "GROUP BY route_id, method\n"
            "HAVING SUM(CASE WHEN snow_day THEN 1 ELSE 0 END) >= 3\n"
            "ORDER BY delta_pct_on_time ASC\n"
            "LIMIT 10"
        ),
        supports=frozenset({"routes"}),
    ),
    Prebuilt(
        label="Equity gaps (high vulnerability, low reliability)",
        explanation=(
            "Ranks stops by priority score, which weights neighborhood vulnerability by half, crash "
            "exposure by 30% and unreliability by 20%, and lists the top 20 with each part's score."
        ),
        sql=(
            "SELECT stop_id, stop_name, priority_score, vuln_score_0_100, crash_score_0_100,\n"
            "  reliability_score_0_100, lat, lon\n"
            "FROM mart_priority_hotspots\n"
            "WHERE reliability_score_0_100 IS NOT NULL{filters}\n"
            "ORDER BY priority_score DESC\n"
            "LIMIT 20"
        ),
        supports=frozenset({"stop"}),
    ),
    Prebuilt(
        label="How often do routes run, and which run every 15 minutes all day?",
        explanation=(
            "Shows each route's scheduled minutes between departures at midday and in the evening, "
            "its first and last departure, and whether it meets the 15-minute frequent standard, "
            "for one direction on weekdays, Saturdays and Sundays."
        ),
        sql=(
            "SELECT route_id, route_name, direction_id, day_type, headway_midday_min,\n"
            "  headway_evening_min, first_departure, last_departure, is_frequent_day, "
            "is_frequent_route\n"
            "FROM mart_frequent_network_by_route\n"
            "WHERE direction_id = 0{filters}\n"
            "ORDER BY is_frequent_route DESC, day_type, headway_midday_min\n"
            "LIMIT 60"
        ),
        supports=frozenset({"routes"}),
    ),
    Prebuilt(
        label="Which routes have the least reliable arrival predictions?",
        explanation=(
            "For predictions shown 6 to 12 minutes before arrival, gives each route's share that "
            "came true within the MBTA's band (2.5 minutes early to 3.5 late), over the chosen "
            "dates, and lists the 10 least accurate routes with at least 200 predictions."
        ),
        sql=(
            "SELECT route_id,\n"
            "  SUM(n_predictions) AS total_predictions,\n"
            "  SUM(pct_within_band * n_predictions) / SUM(n_predictions) AS pct_accurate,\n"
            "  AVG(median_error_sec) AS avg_median_error_sec,\n"
            "  AVG(padding_sec) AS avg_padding_sec\n"
            "FROM mart_prediction_accuracy_by_route_day\n"
            "WHERE horizon_bucket = '6-12'\n"
            "  AND {dates}{filters}\n"
            "GROUP BY route_id\n"
            "HAVING SUM(n_predictions) >= 200\n"
            "ORDER BY pct_accurate ASC\n"
            "LIMIT 10"
        ),
        supports=frozenset({"dates", "routes"}),
        default_window="service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)",
    ),
    Prebuilt(
        label="Which routes missed the most scheduled trips?",
        explanation=(
            "Counts scheduled trips that likely never ran (canceled, no vehicle, or not tracked) as "
            "a share of trips that could be checked, over the chosen dates, and lists the 10 "
            "routes with the highest share among those with at least 50 checkable trips."
        ),
        sql=(
            "SELECT route_id,\n"
            "  SUM(n_observable) AS n_trips_observable,\n"
            "  ROUND(SUM(pct_missed_likely * n_observable)) AS n_missed_likely,\n"
            "  SUM(pct_missed_likely * n_observable) / SUM(n_observable) AS share_missed_likely\n"
            "FROM mart_service_delivered_by_route_day\n"
            "WHERE {dates}\n"
            "  AND pct_missed_likely IS NOT NULL{filters}\n"
            "GROUP BY route_id\n"
            "HAVING SUM(n_observable) >= 50\n"
            "ORDER BY share_missed_likely DESC\n"
            "LIMIT 10"
        ),
        supports=frozenset({"dates", "routes"}),
        default_window=(
            "service_date_mst >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)\n"
            "  AND service_date_mst < CURRENT_DATE"
        ),
    ),
    Prebuilt(
        label="Where are the slowest bus segments at rush hour?",
        explanation=(
            "Lists the 20 slowest stretches between two bus stops on weekdays at 7, 8, 16 and 17 "
            "o'clock, by median speed over the last 28 days, for stretches driven at least 20 times."
        ),
        sql=(
            "SELECT s.route_id, s.direction_id, s.from_stop_name, s.to_stop_name, s.hour_mst,\n"
            "  s.p50_speed_kmh, s.delay_ratio, s.n_traversals, s.lat, s.lon\n"
            "FROM mart_segment_speed_by_hour s\n"
            "JOIN mart_gtfs_routes r USING(route_id)\n"
            "WHERE r.route_type = '3'\n"
            "  AND s.day_type = 'weekday'\n"
            "  AND s.hour_mst IN (7, 8, 16, 17)\n"
            "  AND s.n_traversals >= 20{filters}\n"
            "ORDER BY s.p50_speed_kmh ASC\n"
            "LIMIT 20"
        ),
        supports=frozenset({"routes"}),
        alias="s.",
    ),
]


@dataclass(frozen=True)
class BuiltPrebuilt:
    sql: str
    applied: list[str]
    skipped: list[str]


def build_prebuilt_sql(index: int, filters: Mapping[str, Any] | None = None) -> BuiltPrebuilt:
    """Fill a ready-made question's template with the filters it supports.

    `applied` lists filters that narrowed the SQL; `skipped` lists filters the user set that the
    question doesn't take, or whose values were invalid.
    """
    q = PREBUILT[index]
    f = clean_filters(filters)
    a = q.alias

    builders = {
        "dates": lambda: date_predicate(f, f"{a}service_date_mst"),
        "routes": lambda: route_predicate(f, f"{a}route_id"),
        "stop": lambda: stop_predicate(f, f"{a}stop_id"),
        "weather": lambda: weather_predicate(f, f"{a}precip_bin"),
    }
    applied = [n for n in FILTER_NAMES if n in q.supports and f.is_set(n)]
    # A filter with some invalid values is both applied (the valid ones) and skipped.
    skipped = [n for n in FILTER_NAMES if (f.is_set(n) and n not in applied) or n in f.rejected]

    dates = q.default_window
    if "dates" in applied:
        dates = builders["dates"]()
    extra = [builders[n]() for n in applied if n != "dates"]

    head = q.sql.split("{filters}", 1)[0]
    if not extra:
        rendered = ""
    elif "WHERE" in head:
        rendered = "".join(f"\n  AND {p}" for p in extra)
    else:
        rendered = "\nWHERE " + "\n  AND ".join(extra)

    sql = q.sql.replace("{dates}", dates).replace("{filters}", rendered)
    return BuiltPrebuilt(sql=sql, applied=applied, skipped=skipped)
