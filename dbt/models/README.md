# WhyLine Denver – dbt Models Documentation

**Last Updated**: October 25, 2025

This document describes all 29 dbt models that transform WhyLine Denver's raw transit, weather, crash, and demographic data into analytical marts. These models implement a **medallion architecture** (Bronze → Silver → Gold) using staging, intermediate, and mart layers.

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Staging Models (Silver Layer)](#staging-models-silver-layer)
4. [Intermediate Models (Silver Layer)](#intermediate-models-silver-layer)
5. [Mart Models (Gold Layer)](#mart-models-gold-layer)
6. [Materialization Strategies](#materialization-strategies)
7. [Testing & Data Quality](#testing--data-quality)
8. [Running dbt Locally](#running-dbt-locally)
9. [Deployment & CI/CD](#deployment--cicd)
10. [Additional Resources](#additional-resources)

---

## Overview

WhyLine Denver's dbt project transforms raw ingestion data (`raw_*` tables in BigQuery) into curated analytical datasets (marts) through a systematic refinement process:

```
RAW TABLES (Bronze)
    ↓ dbt sources
STAGING MODELS (Silver) - Deduplicate, normalize, create geometry
    ↓
INTERMEDIATE MODELS (Silver) - Complex derived metrics
    ↓
MART MODELS (Gold) - Domain-specific analytical tables
```

**Key Metrics:**
- **29 total models**: 11 staging + 7 intermediate + 7 marts + 4 exposures
- **4 analytical domains**: Reliability, Safety, Equity, Access
- **40+ dbt tests**: Uniqueness, referential integrity, value ranges, freshness
- **Nightly builds**: Full refresh via GitHub Actions at 9am UTC (2-3am MST)

---

## Project Structure

```
dbt/models/
├── sources_raw.yml          # 13 raw table definitions with freshness checks
├── exposures.yml            # 4 exposures (Streamlit app, exports, docs)
│
├── staging/                 # Silver layer: clean raw data
│   ├── gtfs/               # GTFS static models (routes, stops, trips, etc.)
│   ├── realtime/           # GTFS-RT models (events, daily stats)
│   ├── weather/            # NOAA weather staging
│   ├── crashes/            # Denver crash staging
│   ├── sidewalks/          # Sidewalk infrastructure staging
│   └── census/             # ACS demographics + tract boundaries
│
├── intermediate/            # Silver layer: derived metrics
│   ├── int_rt_events_resolved.sql
│   ├── int_stop_headways_observed.sql
│   ├── int_stop_headways_scheduled.sql
│   ├── int_headway_adherence.sql
│   ├── int_scheduled_arrivals.sql
│   └── int_weather_by_date.sql
│
└── marts/                   # Gold layer: analytical tables
    ├── reliability/         # On-time performance, weather impacts
    ├── safety/              # Crash proximity analysis
    ├── equity/              # Vulnerability scores, priority hotspots
    └── access/              # Pedestrian infrastructure quality
```

---

## Staging Models (Silver Layer)

Staging models (`stg_*`) clean and standardize raw data. They handle deduplication, geometry creation, timezone normalization, and minor transformations. All staging models live in the `stg_denver` BigQuery dataset.

### GTFS Static Models

#### 1. `stg_gtfs_routes`
**Source**: `raw_gtfs_routes`
**Grain**: One row per route
**Materialization**: View

**Purpose**: Deduplicate and expose GTFS route master data.

**Key Columns**:
- `route_id` (PK): Route identifier
- `route_short_name`: Display name (e.g., "15L", "A Line")
- `route_long_name`: Full descriptive name
- `route_type`: GTFS route type enum (bus, rail, etc.)
- `route_color`, `route_text_color`: Hex colors for UI

**Tests**:
- `unique(route_id)`
- `not_null(route_id)`

**Logic**: Ranks by `_extract_date` DESC and takes `rank = 1` to get latest definition.

---

#### 2. `stg_gtfs_stops`
**Source**: `raw_gtfs_stops`
**Grain**: One row per stop
**Materialization**: View

**Purpose**: Deduplicate stops and create `GEOGRAPHY` geometry for spatial joins.

**Key Columns**:
- `stop_id` (PK): Stop identifier
- `stop_name`: Human-readable name
- `stop_lat`, `stop_lon`: WGS84 coordinates
- `geom`: `ST_GEOGPOINT(stop_lon, stop_lat)` for BigQuery spatial functions
- `wheelchair_boarding`: Accessibility flag (0/1/2)

**Tests**:
- `unique(stop_id)`
- `not_null(stop_id, geom)`
- `accepted_values(wheelchair_boarding: [0, 1, 2])`

**Macro Used**: `make_point(lon, lat)` → returns `GEOGRAPHY` type

---

#### 3. `stg_gtfs_trips`
**Source**: `raw_gtfs_trips`, `raw_gtfs_calendar`, `raw_gtfs_calendar_dates`
**Grain**: One row per trip
**Materialization**: View

**Purpose**: Join trip definitions with service calendars and exception dates.

**Key Columns**:
- `trip_id` (PK): Trip identifier
- `route_id` (FK → `stg_gtfs_routes`): Associated route
- `service_id`: Service calendar reference
- `direction_id`: 0/1 for inbound/outbound
- `trip_headsign`: Displayed destination
- `start_date`, `end_date`: Service validity period
- `monday`, `tuesday`, ..., `sunday`: Boolean service days
- `added_service_dates`, `removed_service_dates`: Arrays of exception dates

**Tests**:
- `not_null(trip_id)`
- `relationships(route_id → stg_gtfs_routes.route_id)`

**Logic**: Left join calendar, then left join calendar_dates to handle holiday overrides.

---

#### 4. `stg_gtfs_stop_times`
**Source**: `raw_gtfs_stop_times`
**Grain**: One row per (trip, stop, sequence)
**Materialization**: View

**Purpose**: Expose scheduled arrivals/departures with minimal transformation.

**Key Columns**:
- `trip_id`, `stop_id`, `stop_sequence` (composite PK)
- `arrival_time`, `departure_time`: HH:MM:SS format (may exceed 24:00)
- `timepoint`: Exact time vs. approximate

**Tests**:
- `not_null(trip_id, stop_id)`
- `unique_combination([trip_id, stop_sequence])`

**Note**: No deduplication needed; each GTFS extract replaces prior.

---

### GTFS Realtime Models

#### 5. `stg_rt_events`
**Source**: `raw_gtfsrt_trip_updates`, `raw_gtfsrt_vehicle_positions`, `stg_gtfs_trips`, `int_scheduled_arrivals`
**Grain**: One row per (feed_ts_utc, trip_id, route_id) combination
**Materialization**: **Incremental table**, partitioned by `event_date_mst`, clustered by [`route_id`, `trip_id`]
**unique_key**: `['feed_ts_utc', 'trip_id']`
**Incremental Strategy**: MERGE with dual-lookback windows (3-day incremental, 45-day full-refresh)

**Purpose**: Unified realtime event stream combining trip updates (delays) and vehicle positions (GPS coordinates). Materialized to avoid repeated scans of 5.6 GB raw trip_updates table on every query (Phase 3 cost optimization).

**Key Columns**:
- `feed_ts_utc`: Snapshot timestamp (minute precision)
- `trip_id`, `route_id`: Identifiers
- `stop_id`, `stop_sequence`: Where the delay/position was reported
- `arrival_delay_sec`, `departure_delay_sec`: Seconds ahead/behind schedule
- `schedule_relationship`: GTFS-RT enum (SCHEDULED, SKIPPED, etc.)
- `vehicle_id`, `vehicle_label`: Vehicle identifiers
- `lon`, `lat`, `bearing`, `speed_mps`: GPS data
- `geom`: `ST_GEOGPOINT(lon, lat)` for vehicle position
- `event_ts_utc`: Resolved timestamp of the event (stop time update or vehicle position)
- `direction_id`, `trip_headsign`: Enriched from `stg_gtfs_trips`
- `event_date_mst`, `event_hour_mst`: Timezone-converted for local analysis

**Tests**:
- `not_null(feed_ts_utc, trip_id, route_id)`
- `relationships(route_id → stg_gtfs_routes)`

**Logic**:
1. Full outer join `trip_updates` ↔ `vehicle_positions` on `(feed_ts_utc, trip_id, route_id)`
2. Rank by `event_ts_utc` DESC within each feed to get most recent per trip
3. Left join `stg_gtfs_trips` to enrich with direction/headsign
4. Apply timezone macros: `to_mst_date(event_ts_utc)` → `event_date_mst`

**Macros Used**: `to_mst_date()`, `to_mst_hour()`, `make_point()`

---

### Weather Models

#### 7. `stg_weather`
**Source**: `raw_weather_daily`
**Grain**: One row per (date, station)
**Materialization**: View

**Purpose**: Deduplicate NOAA weather data (rolling 30-day ingest creates overlaps).

**Key Columns**:
- `date`, `station` (composite PK)
- `snow_mm`, `precip_mm`: Precipitation measurements
- `tmin_c`, `tmax_c`, `tavg_c`: Daily temperatures
- `snow_day`: 1 if `snow_mm >= 1`
- `precip_bin`: Enum (`none`, `light`, `mod`, `heavy`)

**Tests**:
- `unique_combination([date, station])`
- `not_null(date, station)`
- `accepted_values(precip_bin: ['none', 'light', 'mod', 'heavy'])`

**Logic**: Rank by `_ingested_at` DESC and filter `rank = 1` (latest ingestion wins).

**Why Deduplication?** NOAA re-ingests a rolling 30-day window nightly to capture finalization. Same date may appear in multiple ingests.

---

### Crash Models

#### 8. `stg_denver_crashes`
**Source**: `raw_crashes`
**Grain**: One row per crash
**Materialization**: View

**Purpose**: Normalize crash data and create geometry for spatial joins.

**Key Columns**:
- `crash_id` (PK): Incident identifier
- `event_ts_utc`: Crash timestamp (converted to UTC)
- `severity`: Enum (`fatal`, `serious_injury`, `injury`, `property_damage`)
- `severity_text`: Original text from source
- `lat`, `lon`: Crash location
- `geom`: `ST_GEOGPOINT(lon, lat)`
- `roadway_name`, `on_route`, `off_route`: Location context
- `bike_involved`, `ped_involved`: 0/1 flags

**Tests**:
- `unique(crash_id)`
- `not_null(crash_id, event_ts_utc, geom)`
- `accepted_values(severity: ['fatal', 'serious_injury', 'injury', 'property_damage'])`

**Macro Used**: `make_point()`

---

### Sidewalk Models

#### 9. `stg_sidewalks`
**Source**: `raw_sidewalks`
**Grain**: One row per sidewalk segment
**Materialization**: View

**Purpose**: Build `LINESTRING` geometry from start/end vertices.

**Key Columns**:
- `sidewalk_id` (PK): Segment identifier
- `class`, `status`, `material`: Attributes
- `year_built`: Construction year
- `lon_start`, `lat_start`, `lon_end`, `lat_end`: Vertices
- `length_m`: Segment length in meters (projected)
- `centroid_lon`, `centroid_lat`: Midpoint
- `geom`: `ST_MAKELINE(ST_GEOGPOINT(...), ST_GEOGPOINT(...))`

**Tests**:
- `not_null(sidewalk_id, geom)`
- `accepted_range(length_m: [0.1, 1000])` (sanity check)

**Macro Used**: `make_line(lon1, lat1, lon2, lat2)`

---

### Census Models

#### 10. `stg_acs_geo`
**Source**: `raw_acs_tract`
**Grain**: One row per census tract
**Materialization**: View

**Purpose**: Normalize ACS demographic data.

**Key Columns**:
- `geoid` (PK): 14000US-prefixed tract GEOID
- `name`: Census tract name
- `year`: ACS release year (2023)
- `hh_no_vehicle`, `hh_total`: Household vehicle ownership
- `workers_transit`, `workers_total`: Commute mode
- `persons_poverty`, `pop_total`: Poverty estimates
- `pct_hh_no_vehicle`, `pct_transit_commute`, `pct_poverty`: Computed ratios (0-1)

**Tests**:
- `unique(geoid)`
- `not_null(geoid)`
- `accepted_range(pct_hh_no_vehicle: [0, 1])`
- `accepted_range(pct_transit_commute: [0, 1])`
- `accepted_range(pct_poverty: [0, 1])`

**Note**: Ratios are precomputed in ingestion; staging exposes as-is.

---

#### 11. `stg_denver_tracts`
**Source**: `raw_denver_tracts`
**Grain**: One row per census tract
**Materialization**: View

**Purpose**: Parse GeoJSON geometry column to `GEOGRAPHY`.

**Key Columns**:
- `geoid` (PK): Census tract GEOID (no 14000US prefix)
- `name`: Tract label
- `aland_m2`, `awater_m2`: Area attributes
- `geom`: `ST_GEOGFROMGEOJSON(geometry_geojson)` → POLYGON/MULTIPOLYGON

**Tests**:
- `unique(geoid)`
- `not_null(geom)`

**Macro Used**: `parse_geojson()`

---

## Intermediate Models (Silver Layer)

Intermediate models (`int_*`) compute complex derived metrics that feed multiple marts. They remain in `stg_denver` dataset but are conceptually part of the transformation pipeline.

#### 1. `int_rt_events_resolved`
**Source**: `stg_rt_events`
**Grain**: One row per event with resolved delay
**Materialization**: View

**Purpose**: Coalesce arrival/departure delays into a single `delay_sec` metric and flag on-time status.

**Key Logic**:
- `delay_sec = COALESCE(arrival_delay_sec, departure_delay_sec, 0)`
- `delay_sec_raw = COALESCE(arrival_delay_sec, departure_delay_sec)` (NULL if both missing)
- `is_on_time = ABS(delay_sec) <= 300` (5-minute threshold)

**Usage**: Feeds reliability marts (`mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`)

---

#### 2. `int_stop_headways_observed`
**Source**: `stg_rt_events`
**Grain**: One row per consecutive arrival pair at same stop
**Materialization**: View

**Purpose**: Compute actual headway (time between consecutive vehicles) from realtime data.

**Key Logic**:
- Window function: `LAG(event_ts_utc) OVER (PARTITION BY route_id, direction_id, stop_id, service_date_mst ORDER BY event_ts_utc)`
- `obs_headway_sec = TIMESTAMP_DIFF(event_ts_utc, prev_event_ts_utc, SECOND)`

**Usage**: Feeds `int_headway_adherence`

---

#### 3. `int_stop_headways_scheduled`
**Source**: `stg_gtfs_stop_times`, `stg_gtfs_trips`, `stg_gtfs_routes`
**Grain**: One row per consecutive scheduled arrival pair at same stop
**Materialization**: View

**Purpose**: Compute scheduled headway from GTFS timetable.

**Key Logic**:
- Convert `arrival_time` (HH:MM:SS) to absolute timestamp using service_date
- Window function to get previous scheduled arrival
- `sch_headway_sec = TIMESTAMP_DIFF(sched_arrival_ts_mst, prev_arrival_ts_mst, SECOND)`

**Usage**: Feeds `int_headway_adherence`

---

#### 4. `int_headway_adherence`
**Source**: `int_stop_headways_observed`, `int_stop_headways_scheduled`
**Grain**: One row per observed arrival with nearest scheduled headway
**Materialization**: View

**Purpose**: Measure whether vehicles maintain scheduled spacing (headway adherence).

**Key Logic**:
1. Join observed ↔ scheduled on nearest timestamp within 30-minute tolerance
2. `headway_adherent = (obs_headway_sec / sch_headway_sec BETWEEN 0.5 AND 1.5)` (±50% tolerance)
3. Only flag adherent if both observed and scheduled > 0

**Usage**: Feeds `mart_reliability_by_stop_hour` for headway metrics

**Why It Matters**: Bunching (short headways) and gaps (long headways) degrade passenger experience even if individual vehicles are "on time."

---

#### 5. `int_scheduled_arrivals`
**Source**: `stg_gtfs_stop_times`, `stg_gtfs_trips`, `stg_gtfs_calendar`, `stg_gtfs_calendar_dates`
**Grain**: One row per scheduled stop arrival across all service dates
**Materialization**: **Materialized table**, partitioned by `service_date_mst`, clustered by [`trip_id`, `stop_id`]
**Rows**: ~22.4M rows spanning 76 days (Sept 25 - Dec 9, 2025)

**Purpose**: Expand GTFS stop_times to absolute timestamps for comprehensive historical analysis. Materialized to avoid re-expanding 22.4M rows on every query (Phase 3 cost optimization).

**Key Logic**:
- Generate date spine from start_date ('2025-09-25') to end_date ('2025-12-09')
- Cross-join with service calendar rules to determine applicable service dates
- `UNNEST(service_dates)` to expand to one row per (trip, stop, date)
- Convert `arrival_time` + `service_date` → `sched_arrival_ts_mst`
- Includes service_date_mst filter fix to prevent delay calculation errors

**Usage**: Feeds `stg_rt_events` (delay calculation), intermediate headway models

**Cost Impact**: Materializing this table reduced per-execution query costs from 15.8GB to 7.5GB (52% reduction)

---

#### 6. `int_weather_by_date`
**Source**: `stg_weather`
**Grain**: One row per service_date_mst
**Materialization**: View

**Purpose**: Denormalize weather data for easy joining to reliability marts.

**Key Logic**: Rename `date` → `service_date_mst` for consistent join key

**Usage**: Feeds `mart_reliability_by_route_day`, `mart_weather_impacts`

---

## Mart Models (Gold Layer)

Mart models (`mart_*`) are the final analytical tables consumed by the Streamlit app, exports, and downstream analysis. They live in the `mart_denver` BigQuery dataset.

### Reliability Domain

#### 1. `mart_reliability_by_route_day`
**Grain**: (route_id, service_date_mst, precip_bin, snow_day)
**Materialization**: **Incremental table**, partitioned by `service_date_mst`, clustered by `route_id`
**Refresh Strategy**: Rebuild last 35 days nightly (to capture late-arriving data)

**Purpose**: Daily on-time performance by route, with weather context.

**Key Columns**:
- `route_id`, `service_date_mst`: Composite key
- `precip_bin`, `snow_day`: Weather conditions from `int_weather_by_date`
- `n_events`: Total realtime events
- `n_reported_events`: Events with non-null delay
- `pct_on_time`: % of events with `|delay| ≤ 300 sec`
- `mean_delay_sec`, `median_delay_sec`, `p90_delay_sec`: Delay distribution

**Incremental Logic**:
```sql
{% if is_incremental() %}
  WHERE service_date_mst > (SELECT MAX(service_date_mst) - INTERVAL 35 DAY FROM {{ this }})
{% endif %}
```

**Tests**:
- `unique_combination([route_id, service_date_mst, precip_bin])`
- `not_null(route_id, service_date_mst)`
- `accepted_range(pct_on_time: [0, 1])`

**Usage**: Primary reliability analysis, weather correlation, route comparison

---

#### 2. `mart_reliability_by_stop_hour`
**Grain**: (stop_id, service_date_mst, event_hour_mst)
**Materialization**: **Incremental table**, partitioned by `service_date_mst`, clustered by `stop_id`
**Refresh Strategy**: Rebuild last 35 days nightly

**Purpose**: Hourly stop-level performance metrics, including headway adherence.

**Key Columns**:
- `stop_id`, `service_date_mst`, `event_hour_mst`: Composite key
- `n_events`: Arrivals at stop during hour
- `pct_on_time`: % on-time arrivals
- `mean_delay_sec`, `p90_delay_sec`: Delay distribution
- `headway_adherence_rate`: % of arrivals maintaining scheduled spacing
- `obs_headway_sec_p50`, `obs_headway_sec_p90`: Observed headway percentiles
- `route_id_mode`: Most common route at stop during hour

**Tests**:
- `unique_combination([stop_id, service_date_mst, event_hour_mst])`
- `accepted_range(pct_on_time: [0, 1])`
- `accepted_range(headway_adherence_rate: [0, 1])`

**Usage**: Peak-hour analysis, stop comparison, headway bunching detection

---

#### 3. `mart_weather_impacts`
**Grain**: (route_id, precip_bin)
**Materialization**: **Table** (full refresh nightly)

**Purpose**: Quantify how precipitation degrades on-time performance by route.

**Key Columns**:
- `route_id`, `precip_bin`: Composite key
- `pct_on_time_avg`: Average on-time % for this route + precip combination
- `pct_on_time_normal`: Baseline on-time % during dry weather (`precip_bin='none'`)
- `delta_pct_on_time`: Impact (negative = degradation) = `pct_on_time_avg - pct_on_time_normal`
- `n_days`, `n_events`: Sample size

**Logic**:
1. Aggregate `mart_reliability_by_route_day` by `(route_id, precip_bin)`
2. Self-join to get baseline performance (`precip_bin='none'`)
3. Calculate delta

**Tests**:
- `unique_combination([route_id, precip_bin])`
- `not_null(pct_on_time_avg)`

**Usage**: Weather vulnerability analysis, resource planning for snow/rain days

---

### Safety Domain

#### 4. `mart_crash_proximity_by_stop`
**Grain**: stop_id (one row per stop)
**Materialization**: **Table** (full refresh nightly)

**Purpose**: Count crashes near transit stops to identify high-risk areas.

**Key Columns**:
- `stop_id`: Primary key
- `as_of_date`: Analysis date (latest crash date)
- `window_days`: Lookback period (365 days)
- `crash_100m_cnt`, `severe_100m_cnt`, `fatal_100m_cnt`: Crashes within 100m
- `crash_250m_cnt`, `severe_250m_cnt`, `fatal_250m_cnt`: Crashes within 250m

**Logic**:
1. Filter crashes to last 365 days: `WHERE event_ts_utc >= CURRENT_TIMESTAMP() - INTERVAL 365 DAY`
2. Spatial join: `ST_DISTANCE(stop.geom, crash.geom) <= 250` (meters)
3. Aggregate counts by distance threshold and severity

**Tests**:
- `unique(stop_id)`
- `not_null(stop_id, as_of_date)`
- `accepted_range(crash_100m_cnt: [0, 1000])`

**Usage**: Safety hotspot identification, Vision Zero analysis

**Note**: Severity levels are numeric (1=property_damage, 2=injury, 3=serious_injury, 4=fatal). `severe_*` counts sum levels 3-4.

---

### Equity Domain

#### 5. `mart_vulnerability_by_stop`
**Grain**: stop_id (one row per stop)
**Materialization**: **Table** (full refresh nightly)

**Purpose**: Composite vulnerability score measuring transit dependence for populations near each stop.

**Key Columns**:
- `stop_id`: Primary key
- `pct_hh_no_vehicle_w`: Weighted % households without cars (within 0.5mi catchment)
- `pct_transit_commute_w`: Weighted % workers using transit
- `pct_poverty_w`: Weighted % below poverty line
- `vuln_score_0_100`: Composite 0-100 score = `(pct_hh_no_vehicle_w + pct_transit_commute_w + pct_poverty_w) / 3 * 100`

**Logic**:
1. For each stop, find census tracts within 0.5 miles (804.672m): `ST_DISTANCE(stop.geom, tract.centroid) <= 804.672`
2. Join tracts to ACS demographics
3. Population-weighted average: `SUM(metric * tract_pop) / SUM(tract_pop)`
4. Compute composite score
5. Min-max normalize to 0-100 scale

**Tests**:
- `unique(stop_id)`
- `accepted_range(vuln_score_0_100: [0, 100])`
- `accepted_range(pct_hh_no_vehicle_w: [0, 1])`

**Usage**: Equity analysis, service prioritization for vulnerable populations

**Why 0.5 miles?** Standard walkable catchment distance for transit access.

---

#### 6. `mart_priority_hotspots`
**Grain**: stop_id (one row per stop)
**Materialization**: **Table** (full refresh nightly)

**Purpose**: Identify stops where vulnerability, low reliability, and crash exposure intersect.

**Key Columns**:
- `stop_id`: Primary key
- `priority_score`: Composite 0-100 score
- `vuln_score`, `reliability_score`, `safety_score`: Component scores

**Logic**:
1. Join `mart_vulnerability_by_stop`, `mart_reliability_by_stop_hour`, `mart_crash_proximity_by_stop`
2. Normalize each component to 0-100 scale
3. Weighted average: `priority_score = 0.4 * vuln_score + 0.3 * (100 - reliability_score) + 0.3 * safety_score`
4. Higher score = higher priority for intervention

**Tests**:
- `unique(stop_id)`
- `accepted_range(priority_score: [0, 100])`

**Usage**: Capital investment prioritization, policy recommendations

**Interpretation**: Stops with high priority scores serve vulnerable populations, have poor service reliability, and face elevated crash risk.

---

### Access Domain

#### 7. `mart_access_score_by_stop`
**Grain**: stop_id (one row per stop)
**Materialization**: **Table** (full refresh nightly)

**Purpose**: Measure pedestrian infrastructure quality near transit access points.

**Key Columns**:
- `stop_id`: Primary key
- `sidewalk_length_m`: Total sidewalk length within 200m buffer
- `sidewalk_segment_count`: Number of segments
- `access_score_0_100`: Normalized density score

**Logic**:
1. For each stop, find sidewalk segments within 200m: `ST_DISTANCE(stop.geom, sidewalk.centroid) <= 200`
2. Sum total length
3. Compute density: `length_m / (PI * 200^2)` (sidewalk length per m² of buffer area)
4. Min-max normalize to 0-100 scale

**Tests**:
- `unique(stop_id)`
- `accepted_range(access_score_0_100: [0, 100])`

**Usage**: First-mile/last-mile analysis, ADA compliance planning

---

## Materialization Strategies

WhyLine Denver implements a **strategic materialization architecture** balancing cost efficiency with query performance, refined through three-phase cost optimization ([detailed case study](../../docs/case-studies/bigquery-cost-optimization-2025.md)):

| Layer | Model | Materialization | Rationale |
|-------|-------|----------------|-----------|
| **Staging (Most)** | stg_gtfs_*, stg_weather, etc. | Views | Lightweight reference tables, always fresh, deduplication logic changes without rebuilds |
| **Staging (RT)** | **stg_rt_events** | **Incremental table** | Avoids repeated scans of 5.6 GB raw trip_updates; 3-day/45-day dual lookback reduces per-execution processing from 15.8GB → 7.5GB |
| **Intermediate (Most)** | int_rt_events_resolved, int_headway_* | Views | Dependency layer, lightweight joins on materialized upstream tables |
| **Intermediate (Schedule)** | **int_scheduled_arrivals** | **Materialized table** | Expands 22.4M rows once instead of re-expanding on every query; eliminates VIEW re-expansion costs for 288 queries/day |
| **Marts (Reliability)** | mart_reliability_*, int_headway_adherence | Incremental tables | Large row counts (10K+ per day), partitioned by date, rebuild only last 3 days with proper unique_keys |
| **Marts (Safety, Equity, Access)** | mart_crash_proximity, mart_vulnerability_*, etc. | Tables | Smaller datasets (<10K rows), spatial joins expensive, full refresh nightly |

### Incremental Processing Patterns

**Pattern 1: Dual-Lookback Windows (stg_rt_events)**
```sql
{% set lookback_days = var('rt_events_lookback_days', 45) %}  -- Full refresh
{% set incremental_days = 3 %}  -- Incremental updates

where feed_ts_utc >= timestamp_sub(current_timestamp(),
  interval {% if is_incremental() %}{{ incremental_days }}{% else %}{{ lookback_days }}{% endif %} day)
```
- **Full refresh**: Process 45 days for comprehensive rebuild
- **Incremental**: Process only 3 days for daily updates
- **Benefit**: Reduces incremental run cost from 5.32 GB → 0.35 GB (15x improvement)

**Pattern 2: Weather-Aware Lookback (Marts)**
```sql
{% set weather_lookback_days = var('weather_lookback_days', 30) %}
{% if is_incremental() %}
  WHERE service_date_mst >= date_sub(current_date("America/Denver"), interval {{ weather_lookback_days }} day)
{% endif %}
```
- **Default 30 days**: Aligns with NOAA rolling re-ingest window (late weather finalization)
- **Why not dynamic MAX(date)?** Expensive subquery scans entire table; fixed lookback uses partition pruning
- **Cost impact**: Use `weather_lookback_days` to balance freshness vs. cost

**Pattern 3: Unique Keys for Proper MERGE**
```sql
{{ config(
    materialized='incremental',
    unique_key=['route_id', 'service_date_mst', 'precip_bin', 'snow_day'],
    ...
) }}
```
- **Critical**: Without unique_key, dbt uses INSERT instead of MERGE, creating duplicates
- **Grain matching**: unique_key must match aggregation grain exactly

### Scalability Achievements

Through Phase 3 strategic materialization (November 2025):
- ✅ Enabled 28x data growth (2-day → 76-day schedule expansion)
- ✅ Reduced per-execution costs 52% (15.8GB → 7.5GB processing)
- ✅ Achieved sustainable $407/month architecture processing 593M+ annual events
- ✅ Prevented $10,268/year cost explosion from naive VIEW-based approach
- ✅ Maintained data quality: All 95 tests passing, no duplicates, correct delay calculations

### When to Materialize vs. Keep as VIEW

**Materialize when:**
- Table scanned 100+ times per day (stg_rt_events: 288x/day)
- Expensive transformation (schedule expansion: 22.4M rows from calendar rules)
- Large source tables (>1 GB raw data)
- Incremental processing can limit window effectively

**Keep as VIEW when:**
- Small reference tables (<100 MB)
- Lightweight joins/filters on already-materialized upstream tables
- Transformation logic changes frequently
- Queried infrequently (<10x/day)

See [BigQuery Cost Optimization Case Study](../../docs/case-studies/bigquery-cost-optimization-2025.md) for complete optimization journey including failed attempts and lessons learned.

---

## Testing & Data Quality

WhyLine Denver enforces data quality through 40+ dbt tests across all models.

### Test Categories

#### 1. **Uniqueness Tests**
Ensure primary keys and composite keys are unique:
- `unique(route_id)` on `stg_gtfs_routes`
- `unique_combination([route_id, service_date_mst, precip_bin])` on `mart_reliability_by_route_day`

#### 2. **Not-Null Tests**
Ensure critical columns are populated:
- `not_null(stop_id, geom)` on `stg_gtfs_stops`
- `not_null(pct_on_time)` on reliability marts

#### 3. **Referential Integrity Tests**
Validate foreign key relationships:
- `relationships(route_id → stg_gtfs_routes.route_id)` on `stg_rt_events`
- `relationships(stop_id → stg_gtfs_stops.stop_id)` on marts

#### 4. **Value Range Tests**
Ensure metrics stay within expected bounds:
- `accepted_range(pct_on_time: [0, 1])`
- `accepted_range(vuln_score_0_100: [0, 100])`
- `accepted_range(length_m: [0.1, 1000])` on sidewalks

#### 5. **Accepted Values Tests**
Validate enum columns:
- `accepted_values(precip_bin: ['none', 'light', 'mod', 'heavy'])`
- `accepted_values(severity: ['fatal', 'serious_injury', 'injury', 'property_damage'])`

#### 6. **Freshness Tests**
Ensure raw data is recent:
```yaml
freshness:
  warn_after: {count: 24, period: hour}
  error_after: {count: 48, period: hour}
```
Applied to `raw_gtfsrt_trip_updates`, `raw_weather_daily`, etc.

### Running Tests

```bash
# Run all tests
make dbt-test-staging
make dbt-test-marts

# Or run specific model tests
DBT_TARGET=prod python -m scripts.dbt_with_env test --project-dir dbt --target prod --select mart_reliability_by_route_day
```

### Test Results in CI/CD

GitHub Actions runs tests nightly after `dbt run`. If any test fails, the workflow alerts and the data team investigates.

**Failure Modes**:
- Uniqueness violation → Duplicate ingestion or deduplication logic broken
- Referential integrity failure → Orphaned records (e.g., trip_id not in stg_gtfs_trips)
- Freshness failure → Ingestion workflow failed or API outage

---

## Running dbt Locally

### Prerequisites

1. **Python 3.11** with dbt-core and dbt-bigquery installed:
   ```bash
   pip install -r requirements.txt
   ```

2. **GCP Credentials**:
   ```bash
   gcloud auth application-default login
   # Or set GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
   ```

3. **Environment Variables** (in `.env`):
   ```bash
   GCP_PROJECT_ID=whyline-denver
   BQ_DATASET_RAW=raw_denver
   BQ_DATASET_STG=stg_denver
   BQ_DATASET_MART=mart_denver
   DBT_PROFILES_DIR=$PWD/dbt/profiles
   ```

### Running dbt Commands

Use the `dbt_with_env.py` helper to inject environment variables:

```bash
# Parse project
make dbt-parse

# Check source freshness
make dbt-source-freshness

# Build staging models
make dbt-run-staging

# Build intermediate models
make dbt-run-intermediate

# Build marts
make dbt-run-marts

# Run tests
make dbt-test-staging
make dbt-test-marts

# Generate documentation
make dbt-docs
# Then open dbt/target/index.html
```

### Development Workflow

1. **Create new model**: Add SQL file to appropriate directory (staging/intermediate/marts)
2. **Add schema YAML**: Document columns, add tests
3. **Parse project**: `make dbt-parse` to validate syntax
4. **Run model**: `python -m scripts.dbt_with_env run --project-dir dbt --target prod --select my_new_model`
5. **Run tests**: `python -m scripts.dbt_with_env test --project-dir dbt --target prod --select my_new_model`
6. **Update dependencies**: If downstream models exist, run them: `--select my_new_model+`

### Targeting Specific Models

```bash
# Run single model
DBT_TARGET=prod python -m scripts.dbt_with_env run --project-dir dbt --select stg_gtfs_routes

# Run model + downstream
DBT_TARGET=prod python -m scripts.dbt_with_env run --project-dir dbt --select stg_gtfs_routes+

# Run model + upstream
DBT_TARGET=prod python -m scripts.dbt_with_env run --project-dir dbt --select +mart_reliability_by_route_day

# Run by tag
DBT_TARGET=prod python -m scripts.dbt_with_env run --project-dir dbt --select tag:reliability

# Run by directory
DBT_TARGET=prod python -m scripts.dbt_with_env run --project-dir dbt --select marts.reliability.*
```

---

## Deployment & CI/CD

dbt models are built nightly via GitHub Actions (see [.github/workflows/README.md](../../.github/workflows/README.md)).

### Nightly BigQuery Workflow

**File**: `.github/workflows/nightly-bq.yml`
**Schedule**: 9am UTC (2-3am MST), after `nightly-ingest.yml`
**Steps**:
1. Parse dbt project (`dbt parse`)
2. Run staging models (`dbt run --select staging.*`)
3. Run intermediate models (`dbt run --select intermediate.*`)
4. Run mart models (`dbt run --select marts.*`)
5. Run tests (`dbt test`)
6. Export marts to GCS (`python -m whylinedenver.sync.export_bq_marts`)
7. Upload artifacts (manifest.json, catalog.json) for dbt docs

**Duration**: ~10-15 minutes
**Cost**: ~$0.02 per run (BigQuery compute)

### Local vs. CI Differences

| Aspect | Local | CI |
|--------|-------|---|
| **Credentials** | ADC (`gcloud auth`) | Service account JSON (GitHub secret) |
| **Target** | `prod` (manually set) | `prod` (hardcoded in workflow) |
| **Parallelism** | Single-threaded | `--threads 4` (faster) |
| **Artifacts** | Local `dbt/target/` | Uploaded to GitHub Actions artifacts |

---

## Additional Resources

- **[Interactive Model Lineage & Docs](https://medsidd.github.io/whyline-denver/)** – Browse all models, view lineage graphs, and explore column-level documentation (auto-deployed from CI)
- **[Root README](../../README.md)** – Project overview, quickstart, FAQ
- **[GitHub Workflows Documentation](../../.github/workflows/README.md)** – How ingestion, dbt, and sync workflows orchestrate
- **[Pipeline Architecture](../../docs/ARCHITECTURE.md)** – Full data flow from ingestion to marts
- **[QA Validation Guide](../../docs/QA_Validation_Guide.md)** – How to validate pipeline health
- **[Data Contracts](../../docs/contracts/CONTRACTS.md)** – Schema specifications for raw ingestion outputs

---

**Questions?** Check the [interactive documentation](https://medsidd.github.io/whyline-denver/) or build locally with `make dbt-docs`. For data quality issues, run the QA script: `./scripts/qa_script.sh`.
