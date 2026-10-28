# Raw data contracts

These contracts describe loader-facing outputs from `src/whyline/ingest/`. The [loader registry](../../src/whyline/load/registry.py) is the executable schema source: each `JobSpec` declares path patterns, destination table, ordered columns, optional partition/clustering, and CSV options. The tables below were reconciled statically from that registry on October 26, 2026, without importing cloud configuration.

CSV field order matters. The loader uses explicit schemas rather than inferring arbitrary files. All source columns in the current registry are `NULLABLE`; source validation/tests may impose stronger expectations. Do not claim a BigQuery REQUIRED constraint merely because a field is normally populated.

Local paths are below `data/raw/`; GCS paths below `gs://<bucket>/raw/`. GTFS text members are extracted alongside a retained ZIP; other registered outputs are gzip CSVs. Not every ingestor uses an identical manifest schema or skip rule.

## `raw_acs_tract`

Patterns: `acs/extract_date=*/acs_tract.csv.gz`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `geoid` | `STRING` | NULLABLE |
| `name` | `STRING` | NULLABLE |
| `year` | `INT64` | NULLABLE |
| `hh_no_vehicle` | `INT64` | NULLABLE |
| `hh_total` | `INT64` | NULLABLE |
| `workers_transit` | `INT64` | NULLABLE |
| `workers_total` | `INT64` | NULLABLE |
| `persons_poverty` | `INT64` | NULLABLE |
| `pop_total` | `INT64` | NULLABLE |
| `pct_hh_no_vehicle` | `NUMERIC` | NULLABLE |
| `pct_transit_commute` | `NUMERIC` | NULLABLE |
| `pct_poverty` | `NUMERIC` | NULLABLE |

## `raw_crashes`

Patterns: `denver_crashes/extract_date=*/crashes.csv.gz`. Physical partition field: `event_ts_utc`.

| Column | BigQuery type | Mode |
|---|---|---|
| `crash_id` | `STRING` | NULLABLE |
| `event_ts_utc` | `TIMESTAMP` | NULLABLE |
| `severity` | `INT64` | NULLABLE |
| `severity_text` | `STRING` | NULLABLE |
| `lat` | `FLOAT64` | NULLABLE |
| `lon` | `FLOAT64` | NULLABLE |
| `roadway_name` | `STRING` | NULLABLE |
| `on_route` | `STRING` | NULLABLE |
| `off_route` | `STRING` | NULLABLE |
| `bike_involved` | `INT64` | NULLABLE |
| `ped_involved` | `INT64` | NULLABLE |

## `raw_sidewalks`

Patterns: `denver_sidewalks/extract_date=*/sidewalks.csv.gz`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `sidewalk_id` | `STRING` | NULLABLE |
| `class` | `STRING` | NULLABLE |
| `status` | `STRING` | NULLABLE |
| `material` | `STRING` | NULLABLE |
| `year_built` | `STRING` | NULLABLE |
| `lon_start` | `FLOAT64` | NULLABLE |
| `lat_start` | `FLOAT64` | NULLABLE |
| `lon_end` | `FLOAT64` | NULLABLE |
| `lat_end` | `FLOAT64` | NULLABLE |
| `length_m` | `FLOAT64` | NULLABLE |
| `centroid_lon` | `FLOAT64` | NULLABLE |
| `centroid_lat` | `FLOAT64` | NULLABLE |

## `raw_denver_tracts`

Patterns: `denver_tracts/extract_date=*/tracts.csv.gz`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `geoid` | `STRING` | NULLABLE |
| `name` | `STRING` | NULLABLE |
| `aland_m2` | `NUMERIC` | NULLABLE |
| `awater_m2` | `NUMERIC` | NULLABLE |
| `geometry_geojson` | `STRING` | NULLABLE |

## `raw_weather_daily`

Patterns: `noaa_daily/extract_date=*/weather.csv.gz`, `noaa_daily/extract_date=*/station=*/weather.csv.gz`. Physical partition field: `date`.

| Column | BigQuery type | Mode |
|---|---|---|
| `date` | `DATE` | NULLABLE |
| `station` | `STRING` | NULLABLE |
| `snow_mm` | `NUMERIC` | NULLABLE |
| `precip_mm` | `NUMERIC` | NULLABLE |
| `tmin_c` | `NUMERIC` | NULLABLE |
| `tmax_c` | `NUMERIC` | NULLABLE |
| `tavg_c` | `NUMERIC` | NULLABLE |
| `snow_day` | `INT64` | NULLABLE |
| `precip_bin` | `STRING` | NULLABLE |

## `raw_gtfs_routes`

Patterns: `rtd_gtfs/extract_date=*/gtfs/routes.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `route_id` | `STRING` | NULLABLE |
| `agency_id` | `STRING` | NULLABLE |
| `route_short_name` | `STRING` | NULLABLE |
| `route_long_name` | `STRING` | NULLABLE |
| `route_desc` | `STRING` | NULLABLE |
| `route_type` | `STRING` | NULLABLE |
| `route_url` | `STRING` | NULLABLE |
| `route_color` | `STRING` | NULLABLE |
| `route_text_color` | `STRING` | NULLABLE |

## `raw_gtfs_stops`

Patterns: `rtd_gtfs/extract_date=*/gtfs/stops.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `stop_id` | `STRING` | NULLABLE |
| `stop_code` | `STRING` | NULLABLE |
| `stop_name` | `STRING` | NULLABLE |
| `stop_desc` | `STRING` | NULLABLE |
| `stop_lat` | `FLOAT64` | NULLABLE |
| `stop_lon` | `FLOAT64` | NULLABLE |
| `zone_id` | `STRING` | NULLABLE |
| `stop_url` | `STRING` | NULLABLE |
| `location_type` | `INT64` | NULLABLE |
| `parent_station` | `STRING` | NULLABLE |
| `stop_timezone` | `STRING` | NULLABLE |
| `wheelchair_boarding` | `INT64` | NULLABLE |
| `platform_code` | `STRING` | NULLABLE |

## `raw_gtfs_trips`

Patterns: `rtd_gtfs/extract_date=*/gtfs/trips.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `route_id` | `STRING` | NULLABLE |
| `service_id` | `STRING` | NULLABLE |
| `trip_id` | `STRING` | NULLABLE |
| `trip_headsign` | `STRING` | NULLABLE |
| `direction_id` | `INT64` | NULLABLE |
| `block_id` | `STRING` | NULLABLE |
| `shape_id` | `STRING` | NULLABLE |

## `raw_gtfs_calendar`

Patterns: `rtd_gtfs/extract_date=*/gtfs/calendar.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `service_id` | `STRING` | NULLABLE |
| `monday` | `INT64` | NULLABLE |
| `tuesday` | `INT64` | NULLABLE |
| `wednesday` | `INT64` | NULLABLE |
| `thursday` | `INT64` | NULLABLE |
| `friday` | `INT64` | NULLABLE |
| `saturday` | `INT64` | NULLABLE |
| `sunday` | `INT64` | NULLABLE |
| `start_date` | `STRING` | NULLABLE |
| `end_date` | `STRING` | NULLABLE |

## `raw_gtfs_calendar_dates`

Patterns: `rtd_gtfs/extract_date=*/gtfs/calendar_dates.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `service_id` | `STRING` | NULLABLE |
| `date` | `STRING` | NULLABLE |
| `exception_type` | `INT64` | NULLABLE |

## `raw_gtfs_stop_times`

Patterns: `rtd_gtfs/extract_date=*/gtfs/stop_times.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `trip_id` | `STRING` | NULLABLE |
| `arrival_time` | `STRING` | NULLABLE |
| `departure_time` | `STRING` | NULLABLE |
| `stop_id` | `STRING` | NULLABLE |
| `stop_sequence` | `INT64` | NULLABLE |
| `stop_headsign` | `STRING` | NULLABLE |
| `pickup_type` | `INT64` | NULLABLE |
| `drop_off_type` | `INT64` | NULLABLE |
| `shape_dist_traveled` | `FLOAT64` | NULLABLE |
| `timepoint` | `INT64` | NULLABLE |

## `raw_gtfs_shapes`

Patterns: `rtd_gtfs/extract_date=*/gtfs/shapes.txt`. Physical partition field: `none`.

| Column | BigQuery type | Mode |
|---|---|---|
| `shape_id` | `STRING` | NULLABLE |
| `shape_pt_lat` | `FLOAT64` | NULLABLE |
| `shape_pt_lon` | `FLOAT64` | NULLABLE |
| `shape_pt_sequence` | `INT64` | NULLABLE |
| `shape_dist_traveled` | `FLOAT64` | NULLABLE |

## `raw_gtfsrt_trip_updates`

Patterns: `rtd_gtfsrt/snapshot_at=*/trip_updates.csv.gz`. Physical partition field: `feed_ts_utc`.

| Column | BigQuery type | Mode |
|---|---|---|
| `feed_ts_utc` | `TIMESTAMP` | NULLABLE |
| `entity_id` | `STRING` | NULLABLE |
| `trip_id` | `STRING` | NULLABLE |
| `route_id` | `STRING` | NULLABLE |
| `stop_id` | `STRING` | NULLABLE |
| `stop_sequence` | `INT64` | NULLABLE |
| `arrival_delay_sec` | `INT64` | NULLABLE |
| `departure_delay_sec` | `INT64` | NULLABLE |
| `schedule_relationship` | `STRING` | NULLABLE |
| `event_ts_utc` | `TIMESTAMP` | NULLABLE |
| `start_date` | `STRING` | NULLABLE |
| `start_time` | `STRING` | NULLABLE |

## `raw_gtfsrt_vehicle_positions`

Patterns: `rtd_gtfsrt/snapshot_at=*/vehicle_positions.csv.gz`. Physical partition field: `feed_ts_utc`.

| Column | BigQuery type | Mode |
|---|---|---|
| `feed_ts_utc` | `TIMESTAMP` | NULLABLE |
| `entity_id` | `STRING` | NULLABLE |
| `trip_id` | `STRING` | NULLABLE |
| `route_id` | `STRING` | NULLABLE |
| `vehicle_id` | `STRING` | NULLABLE |
| `vehicle_label` | `STRING` | NULLABLE |
| `lon` | `FLOAT64` | NULLABLE |
| `lat` | `FLOAT64` | NULLABLE |
| `bearing` | `FLOAT64` | NULLABLE |
| `speed_mps` | `FLOAT64` | NULLABLE |
| `event_ts_utc` | `TIMESTAMP` | NULLABLE |

## Units and source semantics

- Feed/event timestamps are UTC; geographic longitude/latitude outputs use WGS84 degrees. Delays and headways are seconds; speed is meters per second; bearing is degrees.
- Crash `severity` is INT64, not a text category: 1 property damage, 2 injury, 3 serious injury, 4 fatal. `severity_text` retains the mapped source text. Source mapping rules are in `denver_crashes.py`.
- Sidewalk `length_m` is measured in meters using projected calculation; endpoints and centroid are coordinates. Output does not preserve a complete source polyline for every downstream operation.
- Weather uses mm/Celsius. `snow_day` is nullable 0/1 based on at least 1 mm snowfall; precipitation bins are `none`, `light`, `mod`, `heavy`, or null. Route-day `unknown` is a downstream missingness label, not an observed raw precipitation category.
- ACS percentage fields are fractions, not 0–100 values; the registry loads them as NUMERIC. `pct_poverty` uses the configured persons-poverty count divided by total population. GEOIDs are strings to preserve leading zeros/prefixes.
- Tract geometry is serialized GeoJSON; area fields use square meters. A source's valid geometry and county coverage still need validation.

## Loader metadata and manifests

The loader appends four REQUIRED metadata fields: `_ingested_at` TIMESTAMP, `_source_path` STRING, `_extract_date` DATE, and `_hash_md5` STRING. These are not source CSV columns. MD5 tracking prevents identical file reloads, not arbitrary row-level logical duplication.

Most ingestors publish v1 manifests with source, extract/snapshot time, counts, hashes, and quality metadata. GTFS static uses `txt_rows`; realtime/other sources have their own file-level details. The tract ingestor uses a distinct manifest with `dataset`, `record_count`, `generated_at`, and geometry diagnostics rather than the shared v1/hash shape. Follow actual `build_manifest()` or `run()` behavior and [manifest tests](../../tests/ingest/test_manifests.py).

## Contract changes

Coordinate writer, ordered registry schema, loader handling, raw source declarations, staging/marts, fixtures/tests, and documentation. Preserve existing raw files when introducing a new layout or incompatible schema. Use an explicit version/migration plan for incompatible changes; manifest version labels alone do not enforce migrations. A new nullable field is not automatically safe with positional CSV loading.

Current tests cover documented contract/manifests and fixtures under `tests/ingest/` and `tests/fixtures/`; see [testing](../technical/TESTING.md). These tables are loader contracts, not guarantees that every source record satisfies semantic completeness.
