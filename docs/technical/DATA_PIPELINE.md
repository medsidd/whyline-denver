# Data Pipeline

This document traces the complete journey data takes through WhyLine Denver: from external APIs to queryable marts.

## Overview

```
External APIs
     │
     ├─ RTD GTFS Static           (nightly)
     ├─ RTD GTFS-RT               (every 5 min)
     ├─ Denver Open Data Crashes  (nightly)
     ├─ Denver Open Data Sidewalks(nightly)
     ├─ NOAA Weather API          (nightly)
     ├─ Census ACS API            (annually)
     └─ Census TIGER tracts       (manually/annually)
     │
     ▼
GCS raw storage  (gs://whylinedenver-raw/raw/)
     │
     ▼
BigQuery raw_denver (13 tables)
     │
     ▼
dbt stg_denver: staging (10 views) + intermediate (6 models)
     │
     ▼
dbt mart_denver: 9 marts (2 incremental time-series + 7 snapshot tables)
     │
     ▼
GCS Parquet exports (gs://whylinedenver-raw/marts/)
     │
     ▼
DuckDB warehouse  (data/warehouse.duckdb  or  /mnt/gcs/marts/duckdb/warehouse.duckdb)
     │
     ▼
FastAPI → Next.js dashboard
```

---

## Stage 1: Ingestion

Seven independent ingestion scripts live in `src/whyline/ingest/`. Each is a standalone CLI runnable with `python -m whyline.ingest.<module>` or via `make ingest-<name>`. All write to either local `data/raw/` or GCS, controlled by `--local` (default) or `--gcs --bucket <bucket>`.

### Ingestor Inventory

| Module | Make target | Source URL | Output path pattern | Schedule |
|--------|-------------|-----------|---------------------|----------|
| `gtfs_static` | `ingest-gtfs-static` | `https://www.rtd-denver.com/files/gtfs/google_transit.zip` | `raw/rtd_gtfs/extract_date={date}/` | Nightly (8 AM UTC) |
| `gtfs_realtime` | `ingest-gtfs-rt` | `https://www.rtd-denver.com/files/gtfs-rt/TripUpdate.pb` + `VehiclePosition.pb` | `raw/rtd_gtfsrt/snapshot_at={datetime}/` | Every 5 min via Cloud Scheduler |
| `denver_crashes` | `ingest-crashes` | Denver Open Data ArcGIS FeatureServer (5-year rolling window) | `raw/denver_crashes/extract_date={date}/` | Nightly (8 AM UTC) |
| `denver_sidewalks` | `ingest-sidewalks` | Denver Open Data ArcGIS FeatureServer | `raw/denver_sidewalks/extract_date={date}/` | Nightly (8 AM UTC) |
| `noaa_daily` | `ingest-noaa` | `https://www.ncei.noaa.gov/cdo-web/api/v2/data` (station USW00023062) | `raw/noaa_daily/extract_date={date}/` | Nightly (8 AM UTC) |
| `acs` | `ingest-acs` | `https://api.census.gov/data` (ACS 5-year, 2023 vintage, Denver County tracts) | `raw/acs/extract_date={date}/` | Annually (manual or nightly) |
| `denver_tracts` | `ingest-tracts` | Census TIGER Web ArcGIS (2020 tract boundaries) | `raw/denver_tracts/extract_date={date}/` | Manually |

### Idempotency and manifests

Every ingestor is idempotent: if a manifest or output file already exists at the target path, the run is skipped without error. Each run writes a `manifest.json` alongside the data with:

```json
{
  "source": "<URL>",
  "extract_date": "YYYY-MM-DD",
  "written_at_utc": "...",
  "row_count": 12345,
  "bytes": 456789,
  "hash_md5": "...",
  "schema_version": "v1"
}
```

MD5 hashes enable downstream deduplication in the BigQuery loader.

### GTFS-RT details

The realtime ingestor captures point-in-time snapshots of RTD's protobuf feeds:
- **Trip Updates** (`TripUpdate.pb`): per-stop arrival/departure delay in seconds, schedule relationship
- **Vehicle Positions** (`VehiclePosition.pb`): lat/lon, bearing, speed, vehicle ID

Each Cloud Run invocation captures 1 snapshot (`--snapshots 1`). Outputs are gzip-compressed CSVs with columns defined in `TRIP_UPDATES_COLUMNS` and `VEHICLE_POSITIONS_COLUMNS` in `gtfs_realtime.py`. Vehicles outside the Denver bounding box (lon: -105.5 to -104.4, lat: 39.4 to 40.2) are flagged in the manifest quality section.

### Required API keys

| Ingestor | Key | Source |
|----------|-----|--------|
| NOAA weather | `NOAA_CDO_TOKEN` | [NOAA CDO](https://www.ncdc.noaa.gov/cdo-web/token) — free |
| Census ACS | `CENSUS_API_KEY` | [Census API](https://api.census.gov/data/key_signup.html) — free, optional |

GTFS, crashes, and sidewalks have no authentication requirement.

---

## Stage 2: BigQuery Load

`src/whyline/load/bq_load.py` loads raw files from GCS into BigQuery's `raw_denver` dataset.

### How it works

1. **Scan**: Finds raw files in GCS within the requested date range
2. **Plan**: Cross-references `__ingestion_log` table; skips any MD5-identical file already loaded
3. **Execute**: Loads CSV/gzip files into partitioned tables in `raw_denver`
4. **Record**: Logs each load to `raw_denver.__ingestion_log` with extract_date, MD5, row count, bytes

### Make targets

```bash
make bq-load              # Load today's data (or yesterday before 6 AM MST)
make bq-load-local        # Load from data/raw/ instead of GCS
make bq-load-realtime     # Load only today's GTFS-RT snapshots (used in 5-min Cloud Run job)
make bq-load-historical FROM=2025-01-01 UNTIL=2025-01-31  # Backfill date range
```

### BigQuery raw tables (in raw_denver)

| Table | Ingestor | Partition column |
|-------|----------|-----------------|
| `raw_gtfs_routes` | gtfs_static | extract_date |
| `raw_gtfs_stops` | gtfs_static | extract_date |
| `raw_gtfs_trips` | gtfs_static | extract_date |
| `raw_gtfs_stop_times` | gtfs_static | extract_date |
| `raw_gtfs_calendar` | gtfs_static | extract_date |
| `raw_gtfs_calendar_dates` | gtfs_static | extract_date |
| `raw_gtfs_shapes` | gtfs_static | extract_date |
| `raw_gtfsrt_trip_updates` | gtfs_realtime | extract_date |
| `raw_gtfsrt_vehicle_positions` | gtfs_realtime | extract_date |
| `raw_crashes` | denver_crashes | extract_date |
| `raw_sidewalks` | denver_sidewalks | extract_date |
| `raw_weather_daily` | noaa_daily | extract_date |
| `raw_acs_tract` | acs | extract_date |
| `raw_denver_tracts` | denver_tracts | extract_date |

---

## Stage 3: dbt Transformation

dbt transforms raw tables into clean, analytics-ready marts using three layers.

**Project**: `whyline_denver_dbt`
**Profile**: `whyline_denver`
**BigQuery datasets**: raw_denver (source) → stg_denver (staging/intermediate) → mart_denver (marts)

### Layer 1: Staging (10 models — all views)

Views that clean and normalize raw source tables. Views mean no storage cost and always-fresh data.

| Model | Source tables | Key output columns |
|-------|---------------|-------------------|
| `stg_gtfs_routes` | raw_gtfs_routes | route_id, route_name, route_long_name, route_type, is_active |
| `stg_gtfs_stops` | raw_gtfs_stops | stop_id, stop_name, stop_lat, stop_lon, geom (POINT) |
| `stg_gtfs_trips` | raw_gtfs_trips, calendar, calendar_dates | trip_id, route_id, service_id, direction_id, added/removed service dates |
| `stg_gtfs_stop_times` | raw_gtfs_stop_times | trip_id, stop_id, stop_sequence, arr/dep times, hour buckets |
| `stg_rt_events` | raw_gtfsrt_trip_updates, vehicle_positions | feed_ts_utc, trip_id, route_id, stop_id, arrival_delay_sec, vehicle coords |
| `stg_denver_crashes` | raw_crashes | crash_id, event_ts_utc, severity (1-4), geom (POINT), bike/ped flags |
| `stg_sidewalks` | raw_sidewalks | sidewalk_id, class, status, length_m, geom (LINESTRING), centroid |
| `stg_weather` | raw_weather_daily | date, snow_mm, precip_mm, tmin/tmax/tavg_c, snow_day, precip_bin |
| `stg_acs_geo` | raw_acs_tract | geoid, year, pct_hh_no_vehicle, pct_transit_commute, pct_poverty |
| `stg_denver_tracts` | raw_denver_tracts | geoid, name, aland_m2, awater_m2, geom (POLYGON/MULTIPOLYGON) |

**Exception**: `stg_rt_events` is materialized as an **incremental table** (not a view) because the raw realtime source is ~5.6 GB. Querying it as a view would scan the full table on every run. The incremental model merges only new snapshots using a 3-day lookback, with a 45-day lookback on full refresh.

### Layer 2: Intermediate (6 models)

Derived metrics and aggregations that serve as inputs to marts.

| Model | Materialization | Key purpose |
|-------|----------------|-------------|
| `int_scheduled_arrivals` | **Table** (partitioned by service_date_mst) | Expands the GTFS schedule into individual scheduled stop arrivals for ~75 days (45 back + 30 forward). ~22M rows. Pre-materializing avoids recomputing the calendar join on every mart run. |
| `int_rt_events_resolved` | View | Coalesces arrival/departure delays from realtime events; applies on-time threshold (300 seconds by default via `on_time_sec` dbt var). |
| `int_stop_headways_scheduled` | View | Calculates scheduled headway intervals between arrivals at each stop using window functions. |
| `int_stop_headways_observed` | View | Calculates observed headway intervals from realtime events (45-day window). |
| `int_headway_adherence` | **Incremental table** (partitioned by service_date_mst) | Joins observed vs scheduled headways; flags adherence within 50% tolerance. 3-day incremental lookback. |
| `int_weather_by_date` | View | Aggregates weather to daily level by service date; filters to configured station (USW00023062). |

### Layer 3: Marts (9 models)

Final analytics-ready tables queried by the dashboard and exported to DuckDB.

#### Reliability domain

**`mart_reliability_by_route_day`** — Incremental table, partitioned by `service_date_mst`, clustered by `route_id`
One row per (route_id, service_date_mst, precip_bin, snow_day). 30-day incremental rebuild window.
Key columns: `route_id`, `service_date_mst`, `precip_bin`, `snow_day`, `n_events`, `pct_on_time`, `mean_delay_sec`, `median_delay_sec`, `p90_delay_sec`

**`mart_reliability_by_stop_hour`** — Incremental table, partitioned by `service_date_mst`, clustered by `stop_id`
One row per (stop_id, service_date_mst, event_hour_mst). 3-day incremental rebuild.
Key columns: `stop_id`, `service_date_mst`, `event_hour_mst`, `pct_on_time`, `mean_delay_sec`, `p90_delay_sec`, `headway_adherence_rate`, `obs_headway_sec_p50`

**`mart_weather_impacts`** — Snapshot table
Compares average on-time performance by precipitation bin against the dry-weather baseline for each route.
Key columns: `route_id`, `precip_bin`, `pct_on_time_avg`, `pct_on_time_normal`, `delta_pct_on_time`

#### Safety domain

**`mart_crash_proximity_by_stop`** — Snapshot table
Counts crashes within 100m and 250m of each stop using spatial joins. Uses a 365-day crash history.
Key columns: `stop_id`, `as_of_date`, `crash_100m_cnt`, `severe_100m_cnt`, `fatal_100m_cnt`, `crash_250m_cnt`, `severe_250m_cnt`, `fatal_250m_cnt`

#### Access domain

**`mart_access_score_by_stop`** — Snapshot table
Measures total sidewalk length within 200m of each stop; min-max normalized to 0–100.
Key columns: `stop_id`, `buffer_m`, `sidewalk_len_m_within_200m`, `access_score_0_100`

#### Equity domain

**`mart_vulnerability_by_stop`** — Snapshot table
Population-weighted average of three ACS indicators for tracts within 0.5 miles of each stop.
Key columns: `stop_id`, `pct_hh_no_vehicle_w`, `pct_transit_commute_w`, `pct_poverty_w`, `vuln_score_0_100`

**`mart_priority_hotspots`** — Snapshot table
Composite priority score: 0.5 × vulnerability + 0.3 × crash exposure + 0.2 × unreliability.
Key columns: `stop_id`, `vuln_score_0_100`, `crash_score_0_100`, `reliability_score_0_100`, `priority_score`, `priority_rank`

#### Reference tables

**`mart_gtfs_stops`** — Snapshot table
Stop reference with lat/lon for dashboard map enrichment.
Key columns: `stop_id`, `stop_name`, `lat`, `lon`

**`mart_gtfs_routes`** — Snapshot table
Route reference for dashboard result enrichment.
Key columns: `route_id`, `route_name`, `route_long_name`, `route_type`

### dbt variables

| Variable | Default | Effect |
|----------|---------|--------|
| `on_time_sec` | `300` | Seconds threshold for on-time classification (5 min) |
| `headway_tol_ratio` | `0.5` | Tolerance ratio for headway adherence |
| `sched_match_tol_sec` | `1800` | Window (seconds) to match realtime events to schedule |
| `weather_station` | `USW00023062` | NOAA station for weather filtering |
| `weather_lookback_days` | `30` | Rolling window for weather impact calculations |

### Running dbt

```bash
make dbt-run-staging        # Run stg_* models
make dbt-run-intermediate   # Run int_* models
make dbt-run-marts          # Run mart_* models
make dbt-run-realtime       # Optimized subset: stg_rt_events + int_* + reliability marts
make dbt-test-staging       # Run dbt tests on staging layer
make dbt-test-marts         # Run dbt tests on mart layer
make dbt-docs               # Generate and serve dbt docs locally
```

---

## Stage 4: Mart Export (BigQuery → GCS Parquet)

`src/whyline/sync/export_bq_marts.py` exports mart tables from BigQuery to GCS as Parquet files.

```bash
make sync-export
```

**Export strategy by mart type:**

| Type | Marts | GCS path pattern | Export behavior |
|------|-------|-----------------|----------------|
| Partitioned | mart_reliability_by_route_day, mart_reliability_by_stop_hour | `gs://whylinedenver-raw/marts/{name}/run_date={date}/` | Exports each partition date separately; accumulates over time |
| Snapshot | All 7 other marts | `gs://whylinedenver-raw/marts/{name}/run_date={latest}/` | Exports full table, keyed to latest run date only |

Export state is tracked in `gs://whylinedenver-raw/state/sync_state.json`:
```json
{
  "bigquery_updated_at_utc": "2025-03-01T09:00:00Z",
  "marts": {
    "mart_reliability_by_route_day": "2025-03-01",
    ...
  }
}
```

---

## Stage 5: DuckDB Refresh (GCS Parquet → DuckDB)

`src/whyline/sync/refresh_duckdb.py` downloads Parquet files from GCS and materializes them as tables in DuckDB.

```bash
make sync-refresh
```

**What gets loaded:**

All 9 marts are "hot" — materialized as DuckDB tables:
- `mart_reliability_by_route_day`
- `mart_reliability_by_stop_hour`
- `mart_weather_impacts`
- `mart_crash_proximity_by_stop`
- `mart_access_score_by_stop`
- `mart_vulnerability_by_stop`
- `mart_priority_hotspots`
- `mart_gtfs_stops`
- `mart_gtfs_routes`

For snapshot marts, only the latest run_date is loaded. For partitioned marts, all available dates are loaded (up to 90 days by default via `DUCKDB_MAX_AGE_DAYS`).

After loading, the updated `warehouse.duckdb` is uploaded back to `gs://whylinedenver-raw/marts/duckdb/warehouse.duckdb` and `sync_state.json` is updated with `duckdb_synced_at_utc`.

**Combined sync:**
```bash
make sync-duckdb   # Runs sync-export then sync-refresh
```

---

## Stage 6: Query

Once data is in DuckDB or BigQuery, queries are served through the FastAPI layer.

**DuckDB on Cloud Run**: The warehouse file lives on GCS-Fuse at `/mnt/gcs/marts/duckdb/warehouse.duckdb`. On first access, the DuckDB engine copies it to `/tmp/warehouse.duckdb` for faster query performance (controlled by `DUCKDB_COPY_LOCAL=1`).

**BigQuery**: Queries go directly to the live `mart_denver` dataset with a dry-run byte estimate first and a 2 GB maximum bytes billed cap.

See [API_REFERENCE.md](API_REFERENCE.md) for the full query API.

---

## Nightly Automation Schedule

| Time (UTC) | What runs | Make target |
|-----------|-----------|-------------|
| 08:00 | Ingest all 7 static sources + load to BigQuery | `make nightly-ingest-bq` |
| 09:00 | dbt staging + intermediate + marts + export to Parquet | `make nightly-bq` |
| 09:30 | DuckDB refresh from Parquet | `make nightly-duckdb` |
| Every 5 min | GTFS-RT snapshot capture | Cloud Scheduler → Cloud Run |
| Every 5 min | GTFS-RT BigQuery load + dbt realtime subset | Cloud Scheduler → Cloud Run |

---

## Local Development Loop

To run a full local pipeline without Cloud Run:

```bash
# Full pipeline: ingest everything locally, then run dbt + sync
make dev-loop-local          # Write to data/raw, skip GCS

# Or with GCS (closer to production):
make dev-loop-gcs            # ingest-all-gcs → bq-load → dbt-run-marts → sync-duckdb
```

To run individual stages:

```bash
make ingest-gtfs-static      # Download today's GTFS zip locally
make bq-load-local           # Load data/raw/ into BigQuery
make dbt-run-marts           # Transform and publish marts
make sync-duckdb             # Export to Parquet + refresh DuckDB
make api-dev                 # Start FastAPI (reads DuckDB)
```
