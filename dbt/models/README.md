# dbt model reference

The source tree contains 34 SQL models in three layers: 12 silver staging models, 13 gold-core models (six dimensions, six facts, one bridge), and nine serving marts. This inventory was reconciled against SQL on October 27, 2026, when the layered model was cut over in production ([#63](https://github.com/medsidd/whyline-denver/pull/63)). Follow each linked definition for the actual SELECT list, dependencies, filters, and incremental key; schema YAML and the generated catalog provide column metadata.

Project `whyline_denver_dbt`, profile `whyline_denver`. `dbt_project.yml` defaults models to views; the core folder defaults to tables; individual SQL config overrides both. Datasets: staging → `stg_denver` (`BQ_DATASET_STG`), core → `core_denver` (`BQ_DATASET_CORE`), marts → `mart_denver` (`BQ_DATASET_MART`). Bronze is `raw_denver`.

## Layers

| Layer | Dataset | Rule |
|---|---|---|
| Bronze | `raw_denver` | As loaded; append-only; every extract retained. Snapshot sources (GTFS static, sidewalks, tracts, ACS) are partitioned by `_extract_date`; realtime by feed time. |
| Silver | `stg_denver` | One cleaned, typed, deduplicated model per source entity. No cross-domain joins or business rules. Rebuildable from bronze. |
| Gold core | `core_denver` | Kimball star schema: conformed dimensions, atomic facts, a bridge. Not exposed to the app. |
| Gold serving | `mart_denver` | The nine app marts: aggregates with dimension attributes appended. Built only from gold core. Exported to DuckDB. |

## Silver (staging)

| Model / SQL | Materialization | Behavior |
|---|---|---|
| [stg_gtfs_stops](staging/stg_gtfs_stops.sql) | view | Every extract, one row per stop within each; point geometry; `is_valid` coordinate check. |
| [stg_gtfs_routes](staging/stg_gtfs_routes.sql) | view | Every extract, one row per route; display name; `is_valid` requires hex route colors. |
| [stg_gtfs_trips](staging/stg_gtfs_trips.sql) | view | Every extract, one row per trip; `is_valid` requires `direction_id` 0/1. |
| [stg_gtfs_stop_times](staging/stg_gtfs_stop_times.sql) | view | Every extract; GTFS time strings; `is_valid` requires `H:MM:SS` times. |
| [stg_gtfs_calendar](staging/stg_gtfs_calendar.sql) | view | Every extract; parsed service periods and weekday flags; `is_valid` requires parseable dates. |
| [stg_gtfs_calendar_dates](staging/stg_gtfs_calendar_dates.sql) | view | Every extract; service exceptions; `is_valid` requires a parseable date and type 1/2. |
| [stg_rt_events](staging/stg_rt_events.sql) | incremental | Trip-update and vehicle-position merge, one row per feed poll × trip, reported delays only, Denver date/hour. Rows without a `trip_id` are dropped. |
| [stg_denver_crashes](staging/stg_denver_crashes.sql) | view | One row per crash; the latest extract wins with a total order, so reruns agree. |
| [stg_sidewalks](staging/stg_sidewalks.sql) | view | Latest extract, one row per segment; line and centroid geometry. |
| [stg_denver_tracts](staging/stg_denver_tracts.sql) | view | Latest extract; tract geometry. |
| [stg_acs_geo](staging/stg_acs_geo.sql) | view | One row per tract and ACS vintage; GEOID conformed to the tract boundaries (no `14000US` prefix). |
| [stg_weather](staging/stg_weather.sql) | view | Latest ingestion per date/station. |

The loader maps CSV columns by position, so a reordered GTFS source file loads into the wrong columns. This happened for trips and calendar from 2025-12-09 to 2026-01-04 and for routes on several days. The `is_valid` flags catch those rows; dimensions and the schedule fact use valid rows only.

## Gold core

Dimensions carry INT64 surrogate keys (`farm_fingerprint` of the natural key and `valid_from`) and an Unknown member at key `-1`. Facts carry the surrogate key of the version valid on their date, plus natural keys so the 15-minute marts avoid dimension joins.

| Model / SQL | Type | Grain / behavior |
|---|---|---|
| [dim_date](core/dim_date.sql) | dimension | One row per date, 2025-01-01 to 60 days ahead; role-plays as service, crash, and weather date. |
| [dim_stop](core/dim_stop.sql) | Type 2 | Stop versions over GTFS extracts. `is_current` = present in the latest extract; `is_latest_version` = last version ever published. |
| [dim_route](core/dim_route.sql) | Type 2 | Route versions; `-1` is Unassigned. |
| [dim_trip](core/dim_trip.sql) | Type 2 | Trip versions (route, service, direction, headsign). |
| [dim_tract](core/dim_tract.sql) | Type 1 | Latest tract boundaries. |
| [dim_sidewalk_segment](core/dim_sidewalk_segment.sql) | Type 1 | Latest sidewalk inventory. |
| [fct_trip_observation](core/fct_trip_observation.sql) | incremental | Feed poll × trip. Reported delay, else event time minus the scheduled time; `delay_sec_raw` keeps NULL when neither exists, `delay_sec` counts it as zero. |
| [fct_scheduled_stop_time](core/fct_scheduled_stop_time.sql) | incremental (insert-overwrite) | Trip × stop sequence × service date, expanded from the GTFS snapshot current on each date. Nightly runs replace today through +30 days; past partitions keep the schedule as published. |
| [fct_stop_arrival](core/fct_stop_arrival.sql) | incremental | Observed stop event with observed headway, nearest scheduled headway, and adherence flag (1,800-second match, 0.5 relative tolerance). |
| [fct_crash](core/fct_crash.sql) | table | One reported crash. |
| [fct_weather_daily](core/fct_weather_daily.sql) | table | Station × date; `precip_bin` and `snow_day` slice the marts. |
| [fct_tract_demographics](core/fct_tract_demographics.sql) | table | Tract × ACS vintage. |
| [bridge_stop_tract](core/bridge_stop_tract.sql) | table | Current stop × tract within 804.672 m; `weighting_factor` is the tract's population share and sums to 1 per stop. |

Bus matrix:

| Fact | date | stop | route | trip | tract |
|---|:-:|:-:|:-:|:-:|:-:|
| `fct_trip_observation` | ✓ | ✓ | ✓ | ✓ | |
| `fct_scheduled_stop_time` | ✓ | ✓ | ✓ | ✓ | |
| `fct_stop_arrival` | ✓ | ✓ | ✓ | | |
| `fct_crash` | ✓ | | | | |
| `fct_weather_daily` | ✓ | | | | |
| `fct_tract_demographics` | | | | | ✓ |
| `bridge_stop_tract` | | ✓ | | | ✓ |

Schedule snapshots: a day's GTFS load counts only if every file loaded that day passed validation. Each date uses the latest such snapshot on or before it; if that snapshot runs no service on the date, the next snapshot is used. Each file then uses its latest valid extract on or before the chosen snapshot, because the loader skips unchanged files. Every date from 2025-10-23 to 30 days ahead has a schedule.

## Gold serving (marts)

| Model / SQL | Materialization | Behavior |
|---|---|---|
| [mart_reliability_by_route_day](marts/reliability/mart_reliability_by_route_day.sql) | incremental | Route/date/precipitation/snow groups; event counts, resolved-delay counts, on-time share, delay quantiles; route names. |
| [mart_reliability_by_stop_hour](marts/reliability/mart_reliability_by_stop_hour.sql) | incremental | Stop/date/hour groups; on-time/delay/headway summaries, modal route; stop name, coordinates, modal route name. |
| [mart_weather_impacts](marts/reliability/mart_weather_impacts.sql) | table | Route/precipitation-bin equal-weight daily average minus dry baseline over 30 days; excludes unknown weather. |
| [mart_access_score_by_stop](marts/access/mart_access_score_by_stop.sql) | table | Current stops; sidewalk length within 200 m and relative access score. |
| [mart_crash_proximity_by_stop](marts/safety/mart_crash_proximity_by_stop.sql) | table | Current stops; counts within 100/250 m over the latest-crash-date anchored 365-day window. |
| [mart_vulnerability_by_stop](marts/equity/mart_vulnerability_by_stop.sql) | table | Current stops; ACS indicators weighted through `bridge_stop_tract`; relative vulnerability score. |
| [mart_priority_hotspots](marts/equity/mart_priority_hotspots.sql) | table | Weighted vulnerability/crash/unreliability score and dense rank. |
| [mart_gtfs_stops](marts/mart_gtfs_stops.sql) | table | Last known version of every stop ever published (ID, name, lat, lon). |
| [mart_gtfs_routes](marts/mart_gtfs_routes.sql) | table | Last known version of every route ever published. |

Marts keep their names, grains, and original column order; descriptive columns are appended at the end (`stop_name`, `lat`, `lon`; `route_name`, `route_long_name`; `route_name_mode`). The per-stop marts cover stops in the latest GTFS extract (8,162 on October 27, 2026); the reference marts keep retired IDs so historical rows still resolve names.

## Windows and grain

- `stg_rt_events` and `fct_trip_observation` merge on `(feed_ts_utc, trip_id)` over a 12-hour window; a full refresh reads `rt_events_lookback_days` (default 45; 400 rebuilds all bronze since 2025-10-23).
- `fct_stop_arrival` and stop-hour reliability use three days incrementally.
- Route-day reliability replaces `route_day_window_days` partitions: 2 on realtime runs, 30 nightly so late weather lands.
- Incremental merges set `incremental_predicates` so BigQuery scans only recent target partitions.
- Nightly schedule refreshes read each GTFS file's 7 most recent extract partitions (`schedule_recent_extracts`), so a bad latest load falls back to an earlier one. `assert_schedule_covers_today` fails if today has no schedule.

Changing source data outside these windows does not repair historical results; rebuild with `--full-refresh`. See [pipeline](../../docs/technical/DATA_PIPELINE.md).

## Mart fields and interpretation

- Route-day: `route_id`, `service_date_mst`, `precip_bin`, nullable `snow_day`, `n_events`, `n_reported_events`, `pct_on_time`, `mean_delay_sec`, `median_delay_sec`, `p90_delay_sec`, `build_run_at`, `route_name`, `route_long_name`.
- Stop-hour: `stop_id`, `service_date_mst`, `event_hour_mst`, event count, on-time/mean/p90 delay, `route_id_mode`, headway adherence and p50/p90 observed headway, build timestamp, `stop_name`, `lat`, `lon`, `route_name_mode`.
- Weather: route/bin average on-time share, dry-day baseline, delta, build timestamp, route names. A missing dry baseline stays null; unknown weather is excluded.
- Crashes: stop, `as_of_date`, `window_days`, 100/250 m total/severe/fatal counts, build timestamp, stop name and coordinates. Severe includes fatal events.
- Access: stop, `buffer_m`, sidewalk length, normalized access score, build timestamp, stop name and coordinates.
- Vulnerability: stop, three population-weighted shares, normalized vulnerability score, build timestamp, stop name and coordinates.
- Priority: stop, vulnerability/crash/unreliability component scores, weighted priority, dense rank, build timestamp, stop name and coordinates.
- GTFS references: stops (ID/name/lat/lon), routes (ID/name/long name/type).

`n_reported_events` counts events with a reported or schedule-derived delay. On-time share uses absolute delay at most 300 seconds by default and counts an unresolved delay as zero. `reliability_score_0_100` is actually unreliability (higher is worse). Priority coalesces missing components to zero. `_mst` date/hour fields use `America/Denver` including DST. These caveats and full formula interpretations are in the [metrics glossary](../../docs/public/METRICS_GLOSSARY.md).

## API, export, and schemas

All nine marts declare `meta.allow_in_app` and are listed in `src/whyline/sync/constants.py`. API exposure requires both; it also needs matching manifest/catalog artifacts. The two GTFS reference marts are not in the seven-mart CSV-download list. DuckDB refresh maintains separate materialization/latest-snapshot sets and reads Parquet by column name, so appended columns load alongside older partitions. See [add a mart](../../docs/technical/guides/ADDING_A_MART.md).

Column descriptions and tests are in [staging schema](staging/schema.yml), [core schema](core/schema.yml), and [mart schema](marts/schema.yml). Raw source declarations live in [sources_raw.yml](sources_raw.yml); custom generic tests in `dbt/macros/tests/`; singular tests in `dbt/tests/`; extract helpers (`latest_extract_date`, `recent_extracts_filter`, `scd2_from_extracts`) in `dbt/macros/extracts.sql`. Generated [dbt docs](https://medsidd.github.io/whyline-denver/) describe the last published artifact, which can differ from a working tree.

## Commands

From the root with the Python environment activated:

```bash
make dbt-parse
make dbt-run-staging
make dbt-run-core
make dbt-run-marts
make dbt-test-staging
make dbt-test-marts
```

Parsing requires profile environment values but no warehouse query. Run/test/compile/docs operations can access BigQuery. `make dbt-docs` generates documentation; it does not start a web server. `make test` uses temporary offline artifacts rather than regenerating production metadata. See [testing](../../docs/technical/TESTING.md).
