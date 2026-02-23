"""Shared constants for sync utilities."""

ALLOWLISTED_MARTS: tuple[str, ...] = (
    "mart_reliability_by_route_day",
    "mart_reliability_by_stop_hour",
    "mart_crash_proximity_by_stop",
    "mart_access_score_by_stop",
    "mart_vulnerability_by_stop",
    "mart_priority_hotspots",
    "mart_weather_impacts",
)

__all__ = ["ALLOWLISTED_MARTS"]
