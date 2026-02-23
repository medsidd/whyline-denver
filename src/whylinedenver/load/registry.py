"""Registry of BigQuery load jobs for WhyLine Denver raw datasets."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from google.cloud import bigquery

from whylinedenver.config import settings


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


@dataclass(frozen=True)
class Clustering:
    """Clustering configuration for a destination table."""

    fields: tuple[str, ...]


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
        patterns=("noaa_daily/extract_date=*/weather.csv.gz",),
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
)
