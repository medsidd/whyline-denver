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
    "mart_prediction_accuracy_by_route_day",
    "mart_crowding_by_route_hour",
    "mart_crowding_by_stop",
    "mart_service_delivered_by_route_day",
    "mart_wait_by_stop_period",
    "mart_wait_by_route_day",
    "mart_segment_speed_by_hour",
    "mart_trip_runtime_by_route_day",
)

# Live views over the 15-minute realtime loads: queryable in the app (BigQuery only), never
# exported to Parquet or DuckDB.
LIVE_MARTS: tuple[str, ...] = ("mart_vehicles_now", "mart_stop_visits_recent")

__all__ = ["ALLOWLISTED_MARTS", "LIVE_MARTS"]
