# dbt model reference

The source tree contains 83 SQL models in three layers: 24 silver staging models, 29 gold-core models (seven dimensions, 19 facts, three bridges), and 30 serving marts. The continuous realtime stream (five silver views, `fct_stop_visit`, `fct_trip_status`) was added for the [realtime stop visits plan](../../docs/technical/plans/realtime-stop-visits.md). This inventory was reconciled against SQL on October 27, 2026, when the layered model was cut over in production ([#63](https://github.com/medsidd/whyline-denver/pull/63)). Follow each linked definition for the actual SELECT list, dependencies, filters, and incremental key; schema YAML and the generated catalog provide column metadata.

Project `whyline_denver_dbt`, profile `whyline_denver`. `dbt_project.yml` defaults models to views; the core folder defaults to tables; individual SQL config overrides both. Datasets: staging → `stg_denver` (`BQ_DATASET_STG`), core → `core_denver` (`BQ_DATASET_CORE`), marts → `mart_denver` (`BQ_DATASET_MART`). Bronze is `raw_denver`.

## Layers

| Layer | Dataset | Rule |
|---|---|---|
| Bronze | `raw_denver` | As loaded; append-only; every extract retained. Snapshot sources (GTFS static, sidewalks, tracts, ACS) are partitioned by `_extract_date`; realtime by feed time. |
| Silver | `stg_denver` | One cleaned, typed, deduplicated model per source entity. No cross-domain joins or business rules. Rebuildable from bronze. |
| Gold core | `core_denver` | Kimball star schema: conformed dimensions, atomic facts, a bridge. Not exposed to the app. |
| Gold serving | `mart_denver` | Aggregates with dimension attributes appended, built only from gold core. The 12 app marts are exported to DuckDB; marts with `allow_in_app: false` build in BigQuery only. |

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
| [stg_gtfs_shapes](staging/stg_gtfs_shapes.sql) | view | Every extract, one `GEOGRAPHY` line per shape with geodesic length and last `shape_dist_traveled`; `is_valid` requires two or more in-range points. |
| [stg_rt_vehicle_positions](staging/stg_rt_vehicle_positions.sql) | view | Stream vehicle reports without repeats, reports over 120 s old, or positions outside the Denver box; carries the poller's along-route projection. Evidence for validation; not read every 15 minutes. |
| [stg_rt_prediction_changes](staging/stg_rt_prediction_changes.sql) | view | Stream trip-update history as changes only (`new`, `changed`, `dropped`, trip-level rows). Evidence for validation. |
| [stg_rt_stop_visits](staging/stg_rt_stop_visits.sql) | view | Final stop visits from the stream poller (`stream_v1`) or the backfill (`backfill_v1`). |
| [stg_rt_trip_status](staging/stg_rt_trip_status.sql) | view | Trip instances the poller closed, with outcome and visit counts. |
| [stg_denver_crashes](staging/stg_denver_crashes.sql) | view | One row per crash in the latest extract: Denver's five-year window as of that day (crashes that aged out are dropped). Duplicates within it are broken with a total order, so reruns agree. |
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
| [fct_stop_visit](core/fct_stop_visit.sql) | incremental (insert-only merge) | Service date × trip × stop sequence: arrival estimate with earliest/latest bounds, method, dwell, schedule, `delay_sec` (NULL when unknown), prediction error. Permanent; full refresh disabled. |
| [fct_trip_status](core/fct_trip_status.sql) | incremental (insert-only merge) | Service date × trip: final relationship, outcome (`completed`, `partial`, `vanished`, `canceled`, `no_static`), first/last seen, visit counts. |
| [fct_prediction_accuracy](core/fct_prediction_accuracy.sql) | incremental (insert-overwrite) | Service date × trip × stop sequence × horizon (1–30 min): the prediction on screen that long before a measured arrival, its error and accuracy band. Nightly runs replace the last `prediction_accuracy_days` (3) complete service dates. Permanent; full refresh disabled. |
| [fct_trip_occupancy](core/fct_trip_occupancy.sql) | incremental (insert-overwrite) | Stop visit (service date × trip × stop sequence): occupancy reports assigned to the stop the vehicle was heading to or at, with the highest level (1 many seats to 5 full). Nightly runs replace the last `crowding_days` (3) service dates. Permanent; full refresh disabled. |
| [fct_stream_health](core/fct_stream_health.sql) | incremental (insert-overwrite) | 15-minute UTC window: distinct vehicle-feed updates (about 30 when complete) and `is_healthy` (at least 24). Nightly runs replace the last `stream_health_days` (3) dates, today's up to now. Permanent; full refresh disabled. |
| [fct_stop_headway](core/fct_stop_headway.sql) | incremental (insert-overwrite) | Stop visit a vehicle made: observed headway since the previous vehicle of the route and direction at the stop, the scheduled headway, delay, day type and period. Nightly runs replace the last `wait_days` (3) service dates; rebuildable from `fct_stop_visit`. |
| [fct_segment_traversal](core/fct_segment_traversal.sql) | incremental (insert-overwrite) | Trip × consecutive stop pair, both ends timed to within 30 s: running time, scheduled time, distance along the shape, speed (over 130 km/h dropped). Nightly runs replace the last `segment_days` (3) service dates; rebuildable from `fct_stop_visit`. |
| [fct_crash](core/fct_crash.sql) | table | One reported crash. |
| [fct_weather_daily](core/fct_weather_daily.sql) | table | Station × date; `precip_bin` and `snow_day` slice the marts. |
| [fct_tract_demographics](core/fct_tract_demographics.sql) | table | Tract × ACS vintage. |
| [fct_ntd_service_month](core/fct_ntd_service_month.sql) | table | Month × NTD mode × type of service: RTD boardings, revenue miles and hours, peak vehicles (National Transit Database, latest extract). |
| [fct_weather_hourly](core/fct_weather_hourly.sql) | table | Station × UTC hour: precipitation, snowfall, temperature, wind (Open-Meteo), with local date and hour. |
| [fct_alert](core/fct_alert.sql) | incremental (merge) | One RTD service alert: first and last seen in the feed, latest cause, effect and text. Permanent; full refresh disabled. |
| [fct_alert_entity_period](core/fct_alert_entity_period.sql) | incremental (merge) | Alert × informed entity × active period, with the snapshots it appeared in. Permanent; full refresh disabled. |
| [fct_micromobility_near_stop](core/fct_micromobility_near_stop.sql) | incremental (insert-overwrite) | Local date × Denver stop × hour × form factor: average Veo vehicles available within 200 m and share of snapshots with none. Each run replaces the last `micromobility_days` (2) dates and today so far. Permanent; full refresh disabled (raw keeps 30 days). |
| [dim_block_group](core/dim_block_group.sql) | Type 1 | Denver block groups with Colorado EnviroScreen percentile and disproportionately impacted type, and DOTI equity score and group. |
| [bridge_stop_block_group](core/bridge_stop_block_group.sql) | table | Current stop × the Denver block group containing it. |
| [bridge_stop_street_safety](core/bridge_stop_street_safety.sql) | table | Current Denver stop: High Injury Network within 30 m and tier, nearest signal, curb ramps within 50 m, bikeway, transit lane and transit signals nearby. |
| [fct_rtd_reported_performance](core/fct_rtd_reported_performance.sql) | table | Month × RTD service category × metric as RTD reported it (operations reports, from January 2025). |
| [bridge_stop_tract](core/bridge_stop_tract.sql) | table | Current stop × tract within 804.672 m; `weighting_factor` is the tract's population share and sums to 1 per stop. |

Bus matrix:

| Fact | date | stop | route | trip | tract |
|---|:-:|:-:|:-:|:-:|:-:|
| `fct_trip_observation` | ✓ | ✓ | ✓ | ✓ | |
| `fct_scheduled_stop_time` | ✓ | ✓ | ✓ | ✓ | |
| `fct_stop_arrival` | ✓ | ✓ | ✓ | | |
| `fct_stop_visit` | ✓ | ✓ | ✓ | ✓ | |
| `fct_trip_status` | ✓ | | ✓ | ✓ | |
| `fct_prediction_accuracy` | ✓ | ✓ | ✓ | ✓ | |
| `fct_trip_occupancy` | ✓ | ✓ | ✓ | ✓ | |
| `fct_stream_health` | ✓ | | | | |
| `fct_stop_headway` | ✓ | ✓ | ✓ | ✓ | |
| `fct_segment_traversal` | ✓ | ✓ | ✓ | ✓ | |
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
| [mart_service_frequency_by_stop](marts/service/mart_service_frequency_by_stop.sql) | table | Scheduled departures per stop, route, direction and hour on the next Wednesday, Saturday and Sunday (`schedule_sample_dates` macro). |
| [mart_frequent_network_by_route](marts/service/mart_frequent_network_by_route.sql) | table | Span, headway by period and TransitCenter frequent-network flags per route, direction and day type, at the busiest stop. |
| [mart_service_intensity_by_tract](marts/service/mart_service_intensity_by_tract.sql) | table | Weekday departures near each tract, shared by population through `bridge_stop_tract`, per 1,000 residents. |
| [mart_prediction_accuracy_by_route_day](marts/realtime/mart_prediction_accuracy_by_route_day.sql) | incremental (insert-overwrite) | Route × service date × horizon bucket: share of predictions within the accuracy band, error percentiles and padding. `allow_in_app: false` until the stop-visit review. |
| [mart_crowding_by_route_hour](marts/realtime/mart_crowding_by_route_hour.sql) | incremental (insert-overwrite) | Route × direction × service date × departure hour: trips with occupancy data and the shares reaching few seats and standing room, plus the usual load point. `allow_in_app: false` until its coverage check. |
| [mart_service_delivered_by_route_day](marts/realtime/mart_service_delivered_by_route_day.sql) | incremental (insert-overwrite) | Route × direction × service date × period: each scheduled trip's outcome (delivered, canceled, no vehicle, vehicle without visits, not tracked) and the delivered and likely-missed shares of trips the feed fully covered. `allow_in_app: false` until the stop-visit review. |
| [mart_wait_by_route_day](marts/realtime/mart_wait_by_route_day.sql) | incremental (insert-overwrite) | Route × service date: expected, scheduled and excess wait over headways scheduled every 15 minutes or better, bunching, gaps, on-time share, p90 delay. `allow_in_app: false` until the stop-visit review. |
| [mart_wait_by_stop_period](marts/realtime/mart_wait_by_stop_period.sql) | table | Stop × route × direction × day type × period over the last 28 service dates: the same, with a frequent or infrequent `service_class`. `allow_in_app: false` until the stop-visit review. |
| [mart_segment_speed_by_hour](marts/realtime/mart_segment_speed_by_hour.sql) | table | Stop pair × route × direction × day type × hour over the last 28 service dates: p50/p10 speed, p50/p90 running time, scheduled time, delay ratio, midpoint `lat`/`lon`. `allow_in_app: false` until the stop-visit review. |
| [mart_trip_runtime_by_route_day](marts/realtime/mart_trip_runtime_by_route_day.sql) | incremental (insert-overwrite) | Route × direction × first/last stop × service date: p50/p90 and scheduled end-to-end run time and buffer time index. `allow_in_app: false` until the stop-visit review. |
| [mart_ridership_by_mode_month](marts/ridership/mart_ridership_by_mode_month.sql) | table | Month × mode: boardings, revenue hours and miles, boardings per revenue hour, change from a year earlier. `allow_in_app: false` until release R3. |
| [mart_weather_impacts_hourly](marts/reliability/mart_weather_impacts_hourly.sql) | table | Route × weather factor × level over 90 days: on-time share and delay in the hour's weather, and the difference from the route's baseline. `allow_in_app: false` until the stop-visit review. |
| [mart_stop_closures](marts/disruptions/mart_stop_closures.sql) | table | Stop × alert: effect, closure flag, routes, from/until, whether in effect now. `allow_in_app: false` until release R2. |
| [mart_alerts_by_route_day](marts/disruptions/mart_alerts_by_route_day.sql) | table | Route × local day × effect: alerts, alert hours, stops named, from 2026-11-02. `allow_in_app: false` until release R2. |
| [mart_micromobility_access_by_stop](marts/access/mart_micromobility_access_by_stop.sql) | table | Denver stop × weekday/weekend × period over 28 days: average scooters and bikes within 200 m, share of time with none. `allow_in_app: false` until Veo's data terms are checked. |
| [mart_service_equity_by_group](marts/equity/mart_service_equity_by_group.sql) | table | Impacted vs other and DOTI equity group × departures per stop, on-time share, excess wait, crowding over 28 days. `allow_in_app: false` until release R2. |
| [mart_stop_walk_safety](marts/safety/mart_stop_walk_safety.sql) | table | Denver stop: the street-safety fields plus plain-language `walk_safety_flags`. `allow_in_app: false` until release R2. |
| [mart_stop_scorecard](marts/scorecards/mart_stop_scorecard.sql) | table | Current stop: service, reliability, wait, predictions, crowding, safety, access, alerts, equity and micromobility over 28 days, each with its count. `allow_in_app: false` until release R4. |
| [mart_route_scorecard](marts/scorecards/mart_route_scorecard.sql) | table | Route: frequency and span, on-time share, excess wait, delivered and missed trips, predictions, crowding, buffer time index, alert hours over 28 days. `allow_in_app: false` until release R4. |
| [mart_reported_vs_measured_by_month](marts/reliability/mart_reported_vs_measured_by_month.sql) | table | Month × service: RTD's reported on-time share beside WhyLine's measured one. `allow_in_app: false` until release R3. |
| [mart_crowding_by_stop](marts/realtime/mart_crowding_by_stop.sql) | table | Stop × route × direction × weekday/weekend × hour over the last 28 service dates: share of visits arriving with few seats or standing room. `allow_in_app: false` until its coverage check. |

Marts keep their names, grains, and original column order; descriptive columns are appended at the end (`stop_name`, `lat`, `lon`; `route_name`, `route_long_name`; `route_name_mode`). The per-stop marts cover stops in the latest GTFS extract (8,162 on October 27, 2026); the reference marts keep retired IDs so historical rows still resolve names.

## Windows and grain

- `stg_rt_events` and `fct_trip_observation` merge on `(feed_ts_utc, trip_id)` over a 12-hour window; a full refresh reads `rt_events_lookback_days` (default 45; 400 rebuilds all bronze since 2025-10-23).
- `fct_stop_arrival` and stop-hour reliability use three days incrementally.
- `fct_prediction_accuracy` and its route-day mart replace the last `prediction_accuracy_days` (3) service dates; the first build starts at `prediction_accuracy_start` (2026-10-29). `fct_trip_occupancy` and the route-hour crowding mart do the same with `crowding_days` and `crowding_start`; the stop crowding mart rebuilds over `crowding_window_days` (28). `fct_stream_health` and the missed-trip mart use `stream_health_days` and `service_delivered_days`; `fct_stop_headway` and the route-day wait mart use `wait_days`, and the stop wait mart `wait_window_days` (28). `fct_segment_traversal` and the run-time mart use `segment_days`, and the segment speed mart `segment_window_days` (28). Prediction changes are read with constant `feed_ts_utc` bounds, from the window's first date to two days after its last.
- `fct_stop_visit` and `fct_trip_status` insert rows loaded in the last `stop_visit_lookback_hours` (6) for service dates from yesterday (`stop_visit_service_days`, 1) and skip keys already present, so a MERGE never rewrites a partition. Older service dates wait in raw for a run with a wider window; the one-off backfill load runs with `stop_visit_backfill: true` and `stream_start_date`.
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
- Scheduled service: departures and average headway by stop and hour; route span, period headways, `min_departures_per_3h` and the `is_frequent_day` / `is_frequent_route` flags; tract departures per 1,000 residents and frequent stops nearby. All describe the published schedule, not service that ran.
- Prediction accuracy: route, `service_date_mst`, `horizon_bucket`, visit and prediction counts, `pct_within_band`, median/p05/p95 error (actual minus predicted), `padding_sec`, shares more than 2 minutes late and 1 minute early, build timestamp.
- Crowding: route-hour trip counts with and without occupancy data, shares of trips reaching few seats or standing room, `peak_stop_id_mode`; stop-hour visit counts and the same shares over 28 days. Shares exclude trips or visits without data.
- Missed trips: scheduled-trip outcome counts, `n_observable`, `stream_healthy`, `pct_tracked_with_vehicle`, `pct_delivered`, `pct_missed_likely` (NULL when the feed didn't cover any trip or the route's vehicles rarely report).
- Wait time: `expected_wait_sec`, `scheduled_wait_sec`, `excess_wait_sec`, `pct_bunched`, `pct_gap`, `pct_on_time`, `p90_delay_sec`, headway counts; the stop mart adds `service_class` and `avg_scheduled_headway_sec`.
- Speed and run time: segment `p50_speed_kmh`, `p10_speed_kmh`, `p50_travel_sec`, `p90_travel_sec`, `scheduled_travel_sec`, `delay_ratio`, midpoint `lat`/`lon`; route run time `p50_runtime_min`, `p90_runtime_min`, `scheduled_runtime_min`, `buffer_time_index`.

`n_reported_events` counts events with a reported or schedule-derived delay. On-time share uses absolute delay at most 300 seconds by default and counts an unresolved delay as zero. `reliability_score_0_100` is actually unreliability (higher is worse). Priority coalesces missing components to zero. `_mst` date/hour fields use `America/Denver` including DST. These caveats and full formula interpretations are in the [metrics glossary](../../docs/public/METRICS_GLOSSARY.md).

## API, export, and schemas

All 30 marts declare `meta.allow_in_app`; the 12 set to true are listed in `src/whyline/sync/constants.py`. API exposure requires both; it also needs matching manifest/catalog artifacts. The two GTFS reference marts are not in the ten-mart CSV-download list. DuckDB refresh maintains separate materialization/latest-snapshot sets and reads Parquet by column name, so appended columns load alongside older partitions. See [add a mart](../../docs/technical/guides/ADDING_A_MART.md).

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
