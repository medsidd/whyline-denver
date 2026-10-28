"""Registry of BigQuery load jobs for WhyLine Denver raw datasets."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from google.cloud import bigquery

from whyline.config import settings


@dataclass(frozen=True)
class Column:
    """Column definition used for both source files and destination tables."""

    name: str
    field_type: str
    mode: str = "NULLABLE"
    description: str | None = None

    def to_bq_field(self) -> bigquery.SchemaField:
        """Convert to a BigQuery SchemaField."""
        return bigquery.SchemaField(
            self.name, self.field_type, mode=self.mode, description=self.description
        )


@dataclass(frozen=True)
class CSVOptions:
    """CSV loading options applied to a job."""

    field_delimiter: str = ","
    quote_character: str = '"'
    skip_leading_rows: int = 1
    allow_quoted_newlines: bool = True
    encoding: str = "UTF-8"
    null_marker: str = ""


@dataclass(frozen=True)
class Partitioning:
    """Partition configuration for a destination table."""

    field: str
    granularity: str = "DAY"  # or "HOUR"
    expiration_days: int | None = None


@dataclass(frozen=True)
class Clustering:
    """Clustering configuration for a destination table."""

    fields: tuple[str, ...]


STREAM_RETENTION_DAYS = 90

META_COLUMNS: tuple[Column, ...] = (
    Column(
        "_ingested_at",
        "TIMESTAMP",
        mode="REQUIRED",
        description="UTC timestamp when the loader wrote this row.",
    ),
    Column(
        "_source_path",
        "STRING",
        mode="REQUIRED",
        description="Original file path or URI for this record batch.",
    ),
    Column(
        "_extract_date",
        "DATE",
        mode="REQUIRED",
        description="Logical extract date derived from the source.",
    ),
    Column(
        "_hash_md5", "STRING", mode="REQUIRED", description="MD5 hash of the source file contents."
    ),
)


@dataclass(frozen=True)
class JobSpec:
    """Definition of a single loadable dataset."""

    name: str
    patterns: tuple[str, ...]
    table: str
    columns: tuple[Column, ...]
    partition: Partitioning | None = None
    clustering: Clustering | None = None
    csv_options: CSVOptions = CSVOptions()

    def fq_table(self, project: str | None = None, dataset: str | None = None) -> str:
        """Return the fully-qualified table id for the job."""
        project = project or settings.GCP_PROJECT_ID
        dataset = dataset or settings.BQ_DATASET_RAW
        return f"{project}.{dataset}.{self.table}"

    def source_schema(self) -> list[bigquery.SchemaField]:
        """Schema for the raw source file."""
        return [column.to_bq_field() for column in self.columns]

    def table_schema(self) -> list[bigquery.SchemaField]:
        """Schema for the final raw table including meta columns."""
        return [*self.source_schema(), *(column.to_bq_field() for column in META_COLUMNS)]


def _cols(*columns: Sequence[str]) -> tuple[Column, ...]:
    """Helper to build column tuples with optional mode."""
    result: list[Column] = []
    for spec in columns:
        if len(spec) == 2:
            name, field_type = spec
            mode = "NULLABLE"
        else:
            name, field_type, mode = spec
        result.append(Column(name, field_type, mode=mode))
    return tuple(result)


JOBS: tuple[JobSpec, ...] = (
    JobSpec(
        name="acs_tract",
        patterns=("acs/extract_date=*/acs_tract.csv.gz",),
        table="raw_acs_tract",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("geoid", "STRING"),
            ("name", "STRING"),
            ("year", "INT64"),
            ("hh_no_vehicle", "INT64"),
            ("hh_total", "INT64"),
            ("workers_transit", "INT64"),
            ("workers_total", "INT64"),
            ("persons_poverty", "INT64"),
            ("pop_total", "INT64"),
            ("pct_hh_no_vehicle", "NUMERIC"),
            ("pct_transit_commute", "NUMERIC"),
            ("pct_poverty", "NUMERIC"),
        ),
    ),
    JobSpec(
        name="denver_crashes",
        patterns=("denver_crashes/extract_date=*/crashes.csv.gz",),
        table="raw_crashes",
        columns=_cols(
            ("crash_id", "STRING"),
            ("event_ts_utc", "TIMESTAMP"),
            ("severity", "INT64"),
            ("severity_text", "STRING"),
            ("lat", "FLOAT64"),
            ("lon", "FLOAT64"),
            ("roadway_name", "STRING"),
            ("on_route", "STRING"),
            ("off_route", "STRING"),
            ("bike_involved", "INT64"),
            ("ped_involved", "INT64"),
        ),
        partition=Partitioning(field="event_ts_utc"),
        clustering=Clustering(fields=("severity",)),
    ),
    JobSpec(
        name="denver_sidewalks",
        patterns=("denver_sidewalks/extract_date=*/sidewalks.csv.gz",),
        table="raw_sidewalks",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("sidewalk_id", "STRING"),
            ("class", "STRING"),
            ("status", "STRING"),
            ("material", "STRING"),
            ("year_built", "STRING"),
            ("lon_start", "FLOAT64"),
            ("lat_start", "FLOAT64"),
            ("lon_end", "FLOAT64"),
            ("lat_end", "FLOAT64"),
            ("length_m", "FLOAT64"),
            ("centroid_lon", "FLOAT64"),
            ("centroid_lat", "FLOAT64"),
        ),
    ),
    JobSpec(
        name="denver_tracts",
        patterns=("denver_tracts/extract_date=*/tracts.csv.gz",),
        table="raw_denver_tracts",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("geoid", "STRING"),
            ("name", "STRING"),
            ("aland_m2", "NUMERIC"),
            ("awater_m2", "NUMERIC"),
            ("geometry_geojson", "STRING"),
        ),
    ),
    JobSpec(
        name="noaa_daily",
        patterns=(
            "noaa_daily/extract_date=*/weather.csv.gz",
            "noaa_daily/extract_date=*/station=*/weather.csv.gz",
        ),
        table="raw_weather_daily",
        columns=_cols(
            ("date", "DATE"),
            ("station", "STRING"),
            ("snow_mm", "NUMERIC"),
            ("precip_mm", "NUMERIC"),
            ("tmin_c", "NUMERIC"),
            ("tmax_c", "NUMERIC"),
            ("tavg_c", "NUMERIC"),
            ("snow_day", "INT64"),
            ("precip_bin", "STRING"),
        ),
        partition=Partitioning(field="date"),
    ),
    JobSpec(
        name="gtfs_routes",
        patterns=("rtd_gtfs/extract_date=*/gtfs/routes.txt",),
        table="raw_gtfs_routes",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("route_id", "STRING"),
            ("agency_id", "STRING"),
            ("route_short_name", "STRING"),
            ("route_long_name", "STRING"),
            ("route_desc", "STRING"),
            (
                "route_type",
                "STRING",
            ),  # Changed from INT64 - RTD now uses string route types like "LX2", "BOLT", etc.
            ("route_url", "STRING"),
            ("route_color", "STRING"),
            ("route_text_color", "STRING"),
            # network_id removed - RTD GTFS feed does not include this optional field
        ),
        clustering=Clustering(fields=("route_id",)),
    ),
    JobSpec(
        name="gtfs_stops",
        patterns=("rtd_gtfs/extract_date=*/gtfs/stops.txt",),
        table="raw_gtfs_stops",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("stop_id", "STRING"),
            ("stop_code", "STRING"),
            ("stop_name", "STRING"),
            ("stop_desc", "STRING"),
            ("stop_lat", "FLOAT64"),
            ("stop_lon", "FLOAT64"),
            ("zone_id", "STRING"),
            ("stop_url", "STRING"),
            ("location_type", "INT64"),
            ("parent_station", "STRING"),
            ("stop_timezone", "STRING"),
            ("wheelchair_boarding", "INT64"),
            ("platform_code", "STRING"),
        ),
        clustering=Clustering(fields=("stop_id",)),
    ),
    JobSpec(
        name="gtfs_trips",
        patterns=("rtd_gtfs/extract_date=*/gtfs/trips.txt",),
        table="raw_gtfs_trips",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("route_id", "STRING"),
            ("service_id", "STRING"),
            ("trip_id", "STRING"),
            ("trip_headsign", "STRING"),
            ("direction_id", "INT64"),
            ("block_id", "STRING"),
            ("shape_id", "STRING"),
        ),
    ),
    JobSpec(
        name="gtfs_calendar",
        patterns=("rtd_gtfs/extract_date=*/gtfs/calendar.txt",),
        table="raw_gtfs_calendar",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("service_id", "STRING"),
            ("monday", "INT64"),
            ("tuesday", "INT64"),
            ("wednesday", "INT64"),
            ("thursday", "INT64"),
            ("friday", "INT64"),
            ("saturday", "INT64"),
            ("sunday", "INT64"),
            ("start_date", "STRING"),
            ("end_date", "STRING"),
        ),
    ),
    JobSpec(
        name="gtfs_calendar_dates",
        patterns=("rtd_gtfs/extract_date=*/gtfs/calendar_dates.txt",),
        table="raw_gtfs_calendar_dates",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("service_id", "STRING"),
            ("date", "STRING"),
            ("exception_type", "INT64"),
        ),
    ),
    JobSpec(
        name="gtfs_stop_times",
        patterns=("rtd_gtfs/extract_date=*/gtfs/stop_times.txt",),
        table="raw_gtfs_stop_times",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("trip_id", "STRING"),
            ("arrival_time", "STRING"),
            ("departure_time", "STRING"),
            ("stop_id", "STRING"),
            ("stop_sequence", "INT64"),
            ("stop_headsign", "STRING"),
            ("pickup_type", "INT64"),
            ("drop_off_type", "INT64"),
            ("shape_dist_traveled", "FLOAT64"),
            ("timepoint", "INT64"),
        ),
    ),
    JobSpec(
        name="gtfs_shapes",
        patterns=("rtd_gtfs/extract_date=*/gtfs/shapes.txt",),
        table="raw_gtfs_shapes",
        partition=Partitioning(field="_extract_date"),
        columns=_cols(
            ("shape_id", "STRING"),
            ("shape_pt_lat", "FLOAT64"),
            ("shape_pt_lon", "FLOAT64"),
            ("shape_pt_sequence", "INT64"),
            ("shape_dist_traveled", "FLOAT64"),
        ),
    ),
    JobSpec(
        name="gtfsrt_trip_updates",
        patterns=("rtd_gtfsrt/snapshot_at=*/trip_updates.csv.gz",),
        table="raw_gtfsrt_trip_updates",
        columns=_cols(
            ("feed_ts_utc", "TIMESTAMP"),
            ("entity_id", "STRING"),
            ("trip_id", "STRING"),
            ("route_id", "STRING"),
            ("stop_id", "STRING"),
            ("stop_sequence", "INT64"),
            ("arrival_delay_sec", "INT64"),
            ("departure_delay_sec", "INT64"),
            ("schedule_relationship", "STRING"),
            ("event_ts_utc", "TIMESTAMP"),
            ("start_date", "STRING"),
            ("start_time", "STRING"),
        ),
        partition=Partitioning(field="feed_ts_utc"),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    JobSpec(
        name="gtfsrt_vehicle_positions",
        patterns=("rtd_gtfsrt/snapshot_at=*/vehicle_positions.csv.gz",),
        table="raw_gtfsrt_vehicle_positions",
        columns=_cols(
            ("feed_ts_utc", "TIMESTAMP"),
            ("entity_id", "STRING"),
            ("trip_id", "STRING"),
            ("route_id", "STRING"),
            ("vehicle_id", "STRING"),
            ("vehicle_label", "STRING"),
            ("lon", "FLOAT64"),
            ("lat", "FLOAT64"),
            ("bearing", "FLOAT64"),
            ("speed_mps", "FLOAT64"),
            ("event_ts_utc", "TIMESTAMP"),
        ),
        partition=Partitioning(field="feed_ts_utc"),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    # Continuous stream (whyline.ingest.gtfs_rt_stream). Column order must equal the poller's
    # CSV headers (rt_engine *_COLUMNS). Partitions expire; the Coldline archive is permanent.
    # Visits and trip status partition by load hour so backfill rows do not expire on arrival.
    JobSpec(
        name="gtfsrt_tu_changes",
        patterns=("rtd_gtfsrt_stream/snapshot_at=*/tu_changes.csv.gz",),
        table="raw_gtfsrt_tu_changes",
        columns=_cols(
            ("feed_ts_utc", "TIMESTAMP"),
            ("change_type", "STRING"),
            ("trip_id", "STRING"),
            ("start_date", "STRING"),
            ("route_id", "STRING"),
            ("direction_id", "INT64"),
            ("trip_schedule_relationship", "STRING"),
            ("tu_timestamp_utc", "TIMESTAMP"),
            ("tu_vehicle_id", "STRING"),
            ("stop_sequence", "INT64"),
            ("stop_id", "STRING"),
            ("arrival_ts_utc", "TIMESTAMP"),
            ("departure_ts_utc", "TIMESTAMP"),
            ("arrival_delay_sec", "INT64"),
            ("departure_delay_sec", "INT64"),
            ("stop_schedule_relationship", "STRING"),
        ),
        partition=Partitioning(field="feed_ts_utc", expiration_days=STREAM_RETENTION_DAYS),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    JobSpec(
        name="gtfsrt_vp_stream",
        patterns=("rtd_gtfsrt_stream/snapshot_at=*/vp_reports.csv.gz",),
        table="raw_gtfsrt_vp_stream",
        columns=_cols(
            ("feed_ts_utc", "TIMESTAMP"),
            ("report_ts_utc", "TIMESTAMP"),
            ("entity_id", "STRING"),
            ("vehicle_id", "STRING"),
            ("vehicle_label", "STRING"),
            ("trip_id", "STRING"),
            ("start_date", "STRING"),
            ("route_id", "STRING"),
            ("direction_id", "INT64"),
            ("trip_schedule_relationship", "STRING"),
            ("stop_id", "STRING"),
            ("current_status", "STRING"),
            ("lat", "FLOAT64"),
            ("lon", "FLOAT64"),
            ("bearing", "FLOAT64"),
            ("speed_mps", "FLOAT64"),
            ("occupancy_status", "STRING"),
            ("report_age_sec", "INT64"),
            ("is_repeat", "BOOL"),
            ("in_bbox", "BOOL"),
            ("dist_along_m", "FLOAT64"),
            ("lateral_offset_m", "FLOAT64"),
            ("valid_for_timing", "BOOL"),
        ),
        partition=Partitioning(field="feed_ts_utc", expiration_days=STREAM_RETENTION_DAYS),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    JobSpec(
        name="gtfsrt_stop_visits",
        patterns=(
            "rtd_gtfsrt_stream/snapshot_at=*/stop_visits.csv.gz",
            "rtd_gtfsrt_backfill/snapshot_at=*/stop_visits.csv.gz",
        ),
        table="raw_gtfsrt_stop_visits",
        columns=_cols(
            ("service_date", "DATE"),
            ("trip_id", "STRING"),
            ("start_date", "STRING"),
            ("stop_sequence", "INT64"),
            ("stop_id", "STRING"),
            ("stop_role", "STRING"),
            ("route_id", "STRING"),
            ("direction_id", "INT64"),
            ("trip_headsign", "STRING"),
            ("vehicle_id", "STRING"),
            ("arrival_method", "STRING"),
            ("arrival_ts_utc", "TIMESTAMP"),
            ("arrival_earliest_ts", "TIMESTAMP"),
            ("arrival_latest_ts", "TIMESTAMP"),
            ("departure_earliest_ts", "TIMESTAMP"),
            ("departure_latest_ts", "TIMESTAMP"),
            ("dwell_min_sec", "INT64"),
            ("dwell_max_sec", "INT64"),
            ("skipped", "BOOL"),
            ("stopped_observed", "BOOL"),
            ("before_report_ts", "TIMESTAMP"),
            ("before_dist_along_m", "FLOAT64"),
            ("after_report_ts", "TIMESTAMP"),
            ("after_dist_along_m", "FLOAT64"),
            ("stop_dist_m", "FLOAT64"),
            ("nearest_offset_m", "FLOAT64"),
            ("last_predicted_arrival_ts", "TIMESTAMP"),
            ("last_prediction_published_ts", "TIMESTAMP"),
            ("trip_switch_at_terminal", "BOOL"),
            ("low_confidence", "BOOL"),
            ("is_final", "BOOL"),
            ("data_version", "STRING"),
            ("static_md5", "STRING"),
            ("emitted_at", "TIMESTAMP"),
        ),
        partition=Partitioning(
            field="_ingested_at", granularity="HOUR", expiration_days=STREAM_RETENTION_DAYS
        ),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    # Thinned-replay visits for the backfill calibration (backfill engine on stream payloads).
    JobSpec(
        name="gtfsrt_stop_visits_calibration",
        patterns=("rtd_gtfsrt_calibration/snapshot_at=*/stop_visits.csv.gz",),
        table="raw_gtfsrt_stop_visits_calibration",
        columns=_cols(
            ("service_date", "DATE"),
            ("trip_id", "STRING"),
            ("start_date", "STRING"),
            ("stop_sequence", "INT64"),
            ("stop_id", "STRING"),
            ("stop_role", "STRING"),
            ("route_id", "STRING"),
            ("direction_id", "INT64"),
            ("trip_headsign", "STRING"),
            ("vehicle_id", "STRING"),
            ("arrival_method", "STRING"),
            ("arrival_ts_utc", "TIMESTAMP"),
            ("arrival_earliest_ts", "TIMESTAMP"),
            ("arrival_latest_ts", "TIMESTAMP"),
            ("departure_earliest_ts", "TIMESTAMP"),
            ("departure_latest_ts", "TIMESTAMP"),
            ("dwell_min_sec", "INT64"),
            ("dwell_max_sec", "INT64"),
            ("skipped", "BOOL"),
            ("stopped_observed", "BOOL"),
            ("before_report_ts", "TIMESTAMP"),
            ("before_dist_along_m", "FLOAT64"),
            ("after_report_ts", "TIMESTAMP"),
            ("after_dist_along_m", "FLOAT64"),
            ("stop_dist_m", "FLOAT64"),
            ("nearest_offset_m", "FLOAT64"),
            ("last_predicted_arrival_ts", "TIMESTAMP"),
            ("last_prediction_published_ts", "TIMESTAMP"),
            ("trip_switch_at_terminal", "BOOL"),
            ("low_confidence", "BOOL"),
            ("is_final", "BOOL"),
            ("data_version", "STRING"),
            ("static_md5", "STRING"),
            ("emitted_at", "TIMESTAMP"),
        ),
        partition=Partitioning(
            field="_ingested_at", granularity="HOUR", expiration_days=STREAM_RETENTION_DAYS
        ),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
    JobSpec(
        name="gtfsrt_trip_status",
        patterns=(
            "rtd_gtfsrt_stream/snapshot_at=*/trip_status.csv.gz",
            "rtd_gtfsrt_backfill/snapshot_at=*/trip_status.csv.gz",
        ),
        table="raw_gtfsrt_trip_status",
        columns=_cols(
            ("service_date", "DATE"),
            ("trip_id", "STRING"),
            ("start_date", "STRING"),
            ("route_id", "STRING"),
            ("direction_id", "INT64"),
            ("final_schedule_relationship", "STRING"),
            ("outcome", "STRING"),
            ("first_seen_ts", "TIMESTAMP"),
            ("last_seen_ts", "TIMESTAMP"),
            ("first_vp_ts", "TIMESTAMP"),
            ("last_vp_ts", "TIMESTAMP"),
            ("had_vehicle", "BOOL"),
            ("n_stops_static", "INT64"),
            ("n_visits", "INT64"),
            ("n_shape_crossing", "INT64"),
            ("n_last_prediction", "INT64"),
            ("n_skipped", "INT64"),
            ("data_version", "STRING"),
            ("static_md5", "STRING"),
            ("closed_at", "TIMESTAMP"),
        ),
        partition=Partitioning(
            field="_ingested_at", granularity="HOUR", expiration_days=STREAM_RETENTION_DAYS
        ),
        clustering=Clustering(fields=("route_id", "trip_id")),
    ),
)
