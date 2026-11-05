"""Shared constants for sync utilities."""

ALLOWLISTED_MARTS: tuple[str, ...] = (
    "mart_reliability_by_route_day",
    "mart_reliability_by_stop_hour",
    "mart_crash_proximity_by_stop",
    "mart_access_score_by_stop",
    "mart_vulnerability_by_stop",
    "mart_priority_hotspots",
    "mart_weather_impacts",
    "mart_gtfs_stops",
    "mart_gtfs_routes",
    "mart_service_frequency_by_stop",
    "mart_frequent_network_by_route",
    "mart_service_intensity_by_tract",
)

__all__ = ["ALLOWLISTED_MARTS"]
