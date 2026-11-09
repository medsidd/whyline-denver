# Data pipeline

Sixteen ingestion CLIs produce versioned source extracts; one of them, the continuous GTFS-RT poller, runs on a VM and times stop visits itself. BigQuery/dbt build 35 marts. The 20 app marts are exported to Parquet and materialized in DuckDB; two live views read the newest realtime load directly. See [architecture](ARCHITECTURE.md), [raw contracts](../contracts/CONTRACTS.md), and [models](../../dbt/models/README.md) for responsibilities and schemas.

## Ingestion

| Module in `src/whyline/ingest/` | Output below local `data/raw/` or GCS `raw/` | Collection behavior |
|---|---|---|
| `gtfs_static` | `rtd_gtfs/extract_date=…/gtfs/*.txt`, ZIP/current copies and manifest | RTD stops, routes, trips, stop times, calendars, shapes |
| `gtfs_realtime` | `rtd_gtfsrt/snapshot_at=…/{trip_updates,vehicle_positions}.csv.gz` | Sampled protobuf feeds; manifest per snapshot |
| `denver_crashes` | `denver_crashes/extract_date=…/crashes.csv.gz` | Denver ArcGIS, default five-year source window |
| `denver_sidewalks` | `denver_sidewalks/extract_date=…/sidewalks.csv.gz` | Denver ArcGIS geometry normalized into segment fields |
| `noaa_daily` | `noaa_daily/extract_date=…/station=…/weather.csv.gz` | GHCND metric observations; default `USW00003017` |
| `acs` | `acs/extract_date=…/acs_tract.csv.gz` | Configured 2023 ACS five-year estimates, Denver County |
| `denver_tracts` | `denver_tracts/extract_date=…/tracts.csv.gz` | Census TIGERweb 2020 tract geometry, Denver County |
| `gtfs_rt_stream` | `rtd_gtfsrt_stream/snapshot_at=…/{tu_changes,vp_reports,stop_visits,trip_status}.csv.gz`; payload tars in the archive bucket | Continuous poller on the `rt-stream-poller` VM: both feeds every 15 s, stop visits timed from vehicle positions, 15-minute batches. Every payload is archived, including ones the engine failed on, so `--replay` can rebuild them |
| `gtfs_rt_backfill` | `rtd_gtfsrt_backfill/snapshot_at=…/{stop_visits,trip_status}.csv.gz`, loaded into the stream's raw tables | Approximate stop visits from the old 15-minute snapshots (2025-10-23 to the stream's start), `data_version` `backfill_v1`; kept out of the marts until `publish_backfill` is set after calibration |
| `gtfs_alerts` | `rtd_gtfsrt_alerts/snapshot_at=…/` | RTD service alerts, snapshotted by `realtime-load` every 15 minutes |
| `gbfs_veo` | `gbfs_veo/snapshot_at=…/vehicles.csv.gz` | Veo scooter and e-bike availability, snapshotted by `realtime-load` |
| `arcgis_reference` | `arcgis_reference/extract_date=…/` | Weekly Denver and CDPHE reference layers (street safety, equity, sidewalk asset inventory) |
| `ntd_monthly` | `ntd_monthly/extract_date=…/` | RTD monthly ridership and service from the National Transit Database |
| `weather_hourly` | `weather_hourly/extract_date=…/` | Open-Meteo hourly weather at DIA |
| `rtd_reported_performance` | `rtd_reported_performance/extract_date=…/` | RTD's own monthly on-time figures from its operations reports |
| `job_access` | `job_access/extract_date=…/` | Jobs reachable by transit per census tract |

CLIs use `--local` or `--gcs --bucket …`. Most use extract-date output paths; realtime uses minute-level snapshot paths. Existing output/manifest checks vary by ingestor. See module `run()` implementations rather than assuming a universal skip protocol. Most manifests include source, date/time, schema version, row/file counts, hashes, and quality metrics; tract geometry uses a distinct manifest shape. A manifest is not proof of complete data.

`make ingest-all` runs the eleven batch ingestors and writes locally by default; it still makes network requests. The stream poller, its backfill, alerts, Veo and job access run separately. `make ingest-static` runs GTFS static, crashes, sidewalks, NOAA and ACS, then tracts, ArcGIS reference layers, NTD, hourly weather and RTD's reports as nonfatal steps (their failures don't stop the run). ACS is re-extracted nightly but its selected vintage does not advance automatically. Tract geometry is static reference data even though collection is attempted nightly.

`make ingest-gtfs-rt` captures two snapshots 90 seconds apart with the old snapshot collector, whose Cloud Run job (`realtime-ingest`) is paused; realtime data now comes from the stream poller. Weather collection uses a rolling 30-day UTC window through yesterday; absent `NOAA_CDO_TOKEN`, a compatible local CSV is required. The production Census secret is explicitly mapped by the nightly workflow.

## BigQuery loading

`load/registry.py::JOBS` defines 27 raw tables using `JobSpec`, ordered `Column` definitions, path patterns, partitioning, and clustering. The loader does not infer arbitrary new CSV schemas. It adds `_ingested_at`, `_source_path`, `_extract_date`, and `_hash_md5` and tracks loads in `raw_denver.__ingestion_log`. MD5-based skipping prevents repeated identical file loads; it does not guarantee there are no logically duplicate source records across different extracts.

Snapshot sources (GTFS static, sidewalks, tracts, ACS) partition by `_extract_date`, the two snapshot GTFS-RT tables by `feed_ts_utc`, crashes by `event_ts_utc`, and weather by `date`. The four continuous-stream tables expire partitions after 90 days: trip-update changes and vehicle reports partition by `feed_ts_utc` (day), stop visits and trip status by load hour (`_ingested_at`). When the newest stream batch in the load window was sealed more than 30 minutes earlier, the loader logs `STREAM_STALE` (or `STREAM_MISSING` once the stream has ever loaded), which the dead-poller alert matches.

`make bq-load` aliases `bq-load-realtime`: it loads registered GCS sources from today (UTC), or yesterday through today before 06:00 UTC. Despite its name, it is not restricted to GTFS-RT tables. `make bq-load-local` loads local raw files from 2025-01-01. Historical loading accepts `FROM`/`UNTIL`, then also runs selected dbt transformations/tests. All these operations write to BigQuery.

## dbt transformations

The project is `whyline_denver_dbt`, profile `whyline_denver`. It is layered as bronze (`raw_denver`), silver (`stg_denver`), gold core (`core_denver`, a Kimball star schema), and gold serving (`mart_denver`). [The complete inventory](../../dbt/models/README.md) links to every SQL file and lists the bus matrix.

Important materializations/windows:

- `fct_scheduled_stop_time` (core): insert-overwrite by service date. Nightly runs replace today through +30 days from each GTFS file's 7 most recent extract partitions; past partitions keep the schedule as published. A full refresh rebuilds from 2025-10-23, choosing for each date the GTFS snapshot current on it and skipping days whose load failed validation.
- `fct_stop_visit` and `fct_trip_status` (core): insert-only merges of the stream poller's final rows, keyed `(service_date, trip_id, stop_sequence)` and `(service_date, trip_id)`. Each run reads rows loaded in the last 6 hours and skips keys already present, so no partition is rewritten. `service_date` is GTFS `start_date`. Full refresh is disabled because raw stream partitions expire after 90 days.
- Dimensions are rebuilt nightly; `dim_stop`, `dim_route`, and `dim_trip` derive Type 2 history from every bronze extract.
- Route-day reliability: reads `fct_stop_visit`, `fct_trip_status` and `fct_scheduled_stop_time`; partitioned insert-overwrite over `route_day_window_days` (1 on realtime runs, 30 nightly to incorporate weather); excludes null route IDs.
- Stop-hour reliability: reads `fct_stop_visit`; partitioned insert-overwrite over `stop_hour_window_days` (1: yesterday and today, the only service dates `fct_stop_visit` still changes). Both reliability marts disable full refreshes, because their pre-cutover partitions can no longer be rebuilt; to rebuild a longer span, widen the window. The other marts are snapshot tables.
- Legacy, disabled at the stop-visit cutover (their tables are kept, frozen): `stg_rt_events` (silver) and `fct_trip_observation` (core), one row per `(feed_ts_utc, trip_id)` from the 15-minute snapshots, with delay resolved as the reported value, else event time minus the scheduled time; and `fct_stop_arrival` (core), headways between those samples.
- Incremental merges set `incremental_predicates` so BigQuery scans only recent target partitions.

Latest-extract reads go through `latest_extract_date` / `recent_extracts_filter`, which inline the partition date as a constant. A `(select max(_extract_date) ...)` filter does not prune: on October 27, 2026 it scanned 9,958 MiB of `raw_gtfs_stop_times` against 42 MiB for the constant.

On-time share follows RTD's definition (less than one minute early, no more than five minutes late) over visits with a known delay; unknown delays are excluded. Pre-cutover partitions keep the legacy sampled definition. See [metric caveats](../public/METRICS_GLOSSARY.md).

Project variables include `on_time_early_sec=60`, `on_time_late_sec=300`, `headway_tol_ratio=0.5`, `sched_match_tol_sec=1800` (legacy only), `weather_station=USW00003017`, and `weather_lookback_days=30`. `publish_backfill` (default false) admits `backfill_v1` visits into the marts once their calibration is published. Some model defaults are declared locally with `var()`; read SQL before changing a window.

Run layers explicitly for an authorized full build:

```bash
make dbt-run-staging
make dbt-run-core
make dbt-run-marts
make dbt-test-staging
make dbt-test-marts
```

A full rebuild is `dbt run --full-refresh --select staging core marts`. `fct_stop_visit`, `fct_trip_status` and the two reliability marts ignore `--full-refresh` (`full_refresh: false`): raw stream partitions expire after 90 days, and the legacy models behind the pre-cutover mart partitions are disabled. The October 27, 2026 full rebuild, which still included the legacy models, scanned about 40 GiB. The nightly recipe selects `'staging core marts'`, tests `'core marts'`, then exports. The realtime target runs the stream path (`stg_rt_stop_visits stg_rt_trip_status fct_stop_visit fct_trip_status`) and the two reliability marts with `route_day_window_days: 1`; it depends on the dimensions and schedule built nightly and is not a complete DAG bootstrap.

## Weather corrections

Station defaults agree on Denver International Airport (`USW00003017`). CDO responses requested with `units=metric` and local fallback data are interpreted as mm/Celsius, without magnitude-based rescaling. All-missing precipitation extracts fail before publication. New station subdirectories preserve legacy raw files; the loader supports both layouts.

`stg_weather` keeps the newest `_ingested_at` row per date/station. Missing observations remain null; route-day precipitation becomes `unknown` and snow can remain null. Weather comparisons exclude unknown days and use the configured lookback. A comparison can be empty or have a null dry baseline without a pipeline failure.

## Export and DuckDB refresh

`sync/export_bq_marts.py` exports the 20 marts in `sync/constants.py::ALLOWLISTED_MARTS` (never the live views in `LIVE_MARTS`). The seven date-grained marts in `PARTITIONED_MARTS` export by `service_date_mst` into `marts/{mart}/run_date={date}/`; the others export a full snapshot into a run-date directory. Export progress uses BigQuery/GCS state stores; serving freshness is tracked separately in `state/sync_state.json`.

Partition selection includes newer dates and older partitions with a newer `build_run_at`. A bounded corrective export can use:

```bash
PYTHONPATH=src python -m whyline.sync.export_bq_marts   --mart mart_reliability_by_route_day --mart mart_weather_impacts   --since 2026-10-14 --force
```

The date is an example and must be chosen for the intended repair. `--force` replaces derived exports; do not treat it as a read-only check.

`sync/refresh_duckdb.py` materializes all 20 tables, selects latest snapshot runs, and limits partitioned history by `DUCKDB_MAX_AGE_DAYS` (90). It writes `data/warehouse.duckdb` by default, uploads the configured warehouse blob, and updates `duckdb_synced_at_utc`. Local Parquet inputs do not by themselves disable configured upload behavior.

```bash
make sync-export     # BigQuery → GCS, including changed older partitions
make sync-refresh    # Parquet → DuckDB + configured uploads/state
make sync-duckdb     # both, not a file download
```

## Automation and serving

| Trigger | Actual recipe |
|---|---|
| GitHub cron 08:00 UTC | `nightly-ingest-bq`: static-source collection + date-window raw loading |
| GitHub cron 09:00 UTC | `nightly-bq`: selected transformations, mart tests, export; workflow updates BigQuery timestamp |
| GitHub cron 09:30 UTC | `nightly-duckdb`: warehouse refresh |
| Stream poller on the `rt-stream-poller` VM, continuous | Reads both realtime feeds every 15 s and publishes a batch every 15 minutes |
| Cloud Scheduler, every 15 minutes (`realtime-load`) | Snapshots alerts and Veo vehicles, loads new raw files including the poller's batches, runs the six-model `dbt-run-realtime` subset (the two stream views, `fct_stop_visit`, `fct_trip_status` and the two reliability marts), and updates the timestamp. `realtime-ingest`, the old snapshot capture, is paused |

GitHub cron starts can be delayed. These workflows have no completion dependency between each other. Verify upstream completion before a manual sequential recovery. The two realtime GitHub workflows are manual fallbacks, not the recurring scheduler.

The API queries BigQuery or a local copy of the GCS-mounted DuckDB warehouse. Cached connections/results/lookups can differ from the newest file/state. Verify real results as well as `/api/health` and `/api/freshness`; see [QA validation](../QA_Validation_Guide.md).
