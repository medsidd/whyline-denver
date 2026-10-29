# Metrics glossary

These definitions describe current SQL behavior. Fractions are normally 0–1, scores 0–100, delays seconds, distances meters, precipitation/snow mm, and temperatures Celsius. Inspect SQL and observation coverage before comparing values across engines/dates.

## Reliability

The reliability marts count **stop visits** (`core.fct_stop_visit`): one row per service date, trip and stop sequence, recording when the vehicle serving that trip reached the stop. The stream poller times visits from vehicle reports sent about every 30 seconds ([how a visit is timed](#how-a-visit-is-timed)). Partitions built before the stop-visit cutover keep the legacy sampled method, and their `data_version` is NULL ([legacy partitions](#legacy-partitions-before-the-cutover)).

| Field | Current calculation and meaning |
|---|---|
| `n_events` | Stop visits with an arrival in the group; skipped stops are excluded |
| `n_reported_events` | Visits with a known delay (an arrival and a scheduled time); the denominator for on-time and delay statistics |
| `pct_on_time` | Share of visits with a known delay that arrived less than one minute early and no more than five minutes late, RTD's definition (`-60 < delay_sec <= 300`). At a trip's first stop the departure is compared instead. Unknown delays are excluded; NULL when no visit in the group has one. |
| `mean_delay_sec` | Mean of known delays; negative means early |
| `median_delay_sec`, `p90_delay_sec` | Approximate 50th/90th percentiles of known delays (route-day; stop-hour has p90) |
| `n_scheduled` | Route-day: scheduled stop events (`fct_scheduled_stop_time`), canceled trips included |
| `pct_observed` | Route-day: share of scheduled stop events with an observed visit. Canceled trips and trips that never reported count against it; trips missing from the schedule don't count. The current day's value rises as the day goes on. |
| `n_skipped` | Route-day: stops RTD marked SKIPPED on trips that ran |
| `n_canceled_trips` | Route-day: trips RTD canceled (`fct_trip_status`) |
| `pct_shape_crossing` | Share of visits timed from vehicle positions (origin departures included) |
| `pct_last_prediction` | Route-day: share of visits timed from RTD's final prediction |
| `pct_within_30s` | Share of visits whose arrival window (`arrival_latest_ts` − `arrival_earliest_ts`) is at most 30 seconds |
| `median_window_sec` | Route-day: median arrival window in seconds |
| `data_version` | `stream_v1`, `backfill_v1` (only once its calibration is published), `mixed`, or NULL for legacy partitions |
| `headway_adherence_rate` | Stop-hour: share of visits whose observed headway is within 50% of the scheduled headway. The observed headway is the time since the previous visit at the stop by the same route and direction on that service date; the scheduled headway is the gap to the previous scheduled trip. Visits lacking either aren't judged, and a missed trip shows up as a long observed headway. |
| `obs_headway_sec_p50`, `obs_headway_sec_p90` | Approximate percentiles of those observed headways |
| `route_id_mode` | Most frequently observed route in a stop/date/hour group; not a complete route breakdown |

### How a visit is timed

| `arrival_method` | How the arrival was found | Window |
|---|---|---|
| `shape_crossing` | The vehicle's distance along the route shape crossed the stop between two valid reports at most 30 s apart; the arrival is interpolated between them | ≤ 30 s |
| `shape_crossing_gap` | The same, with the two reports more than 30 s apart | > 30 s |
| `origin_departure` | First stop of a trip: the departure, between the last report at the stop and the next report | one report interval |
| `last_prediction` | No usable crossing: RTD's final predicted arrival, used only when the trip had demonstrably run and the prediction had come due | from the earlier of its first publication and the value − 60 s, to the first refresh without the stop |
| `skipped` | RTD marked the stop SKIPPED; no arrival | — |
| `backfill_shape_crossing`, `backfill_prediction` | The same rules applied to the 15-minute snapshots kept before the stream started (`backfill_v1`) | minutes |

Every visit keeps `arrival_earliest_ts` and `arrival_latest_ts`, so its own uncertainty travels with it. A stop's arrival point is the stop pole's distance along the shape, or the first STOPPED_AT report at that stop when the vehicle stopped short of the pole. Interpolation assumes constant speed between the two reports, so it slightly favours early estimates for a bus decelerating into the stop; the dual run measures that bias against STOPPED_AT reports. Reports are used only when they are fresh (at most 120 s old), inside the Denver bounding box and within 100 m of the shape; detours and layovers therefore leave gaps. Trains report less often than buses (light rail p90 gap 76 s), so rail windows are wider. In a 20-minute sample on October 28, 2026, 85% of bus visits fell within 30 s, against 25% for light rail and 30% for commuter rail. RTD's canceled trips get no visits; they appear in `fct_trip_status` with outcome `canceled`.

### Changed definitions at the cutover

| Field | Legacy (sampled) | Stop visits |
|---|---|---|
| Unit counted | One sampled prediction per 15-minute poll and trip, usually of the trip's terminal arrival | One visit per trip and stop |
| `n_events` | Poll × trip samples | Visits with an arrival |
| `n_reported_events` | Samples with a reported or schedule-derived delay | Visits with a known delay |
| `pct_on_time` | `ABS(delay_sec) <= 300`; unknown delays counted as on time | `-60 < delay_sec <= 300` (RTD); unknown delays excluded |
| `mean_delay_sec`, `median_delay_sec`, `p90_delay_sec` | Unknown delays counted as zero | Known delays only |
| `service_date_mst` | Denver date of the poll | GTFS service date (`start_date`): a trip running past midnight belongs to the day it began |
| `event_hour_mst` (stop-hour) | Hour of the sampled event | Hour of the arrival, Denver time |
| Headways | Between sampled predicted terminal arrivals, matched to the nearest scheduled headway within 1,800 s | Between consecutive visits by the same route and direction, against that visit's scheduled headway |

Appended columns: route-day `data_version`, `n_skipped`, `n_canceled_trips`, `n_scheduled`, `pct_observed`, `pct_shape_crossing`, `pct_last_prediction`, `pct_within_30s`, `median_window_sec`; stop-hour `data_version`, `n_reported_events`, `pct_within_30s`, `pct_shape_crossing`. `mart_weather_impacts` and the priority ranking's unreliability score read `pct_on_time`, so they change too, and their 30- and 35-day windows mix both methods for a month after the cutover.

### Legacy partitions before the cutover

Partitions built before the cutover come from `fct_trip_observation` (now frozen): one sampled prediction per 15-minute poll and trip, usually of its terminal arrival, not an observed stop arrival. Its delay is the reported arrival delay, otherwise the reported departure delay, otherwise event time minus the scheduled time for the same trip, stop, and date, otherwise zero. A delay still missing after that counts as on-time. Until the October 27, 2026 rebuild the schedule table was stale, so January and April–August 2026 showed about 100% on-time; the rebuild recomputed all history since October 23, 2025 with the schedule current on each date (about 77% on-time in those months). This is not a census of verified physical arrivals. Staging selects one row per `(feed_ts_utc, trip_id)`, so feed coverage and selection affect every aggregate.

Legacy headways were computed between those sampled event timestamps by route/direction/stop/date, with the nearest scheduled headway accepted within 1,800 seconds and adherence within 50% of a positive scheduled headway. They describe available samples, not complete service intervals.

The backfill (`backfill_v1`) recomputes the earlier dates as stop visits from the 15-minute snapshots. It stays out of the marts until it has been calibrated against the stream; the calibration (median and p90 absolute error, bias, coverage loss) will be recorded here when it is published.

## Weather

| `precip_bin` | Source precipitation total |
|---|---|
| `none` | Zero or less (nonpositive values are classified dry by the implementation) |
| `light` | Greater than 0 and at most 5 mm |
| `mod` | Greater than 5 and at most 20 mm |
| `heavy` | Greater than 20 mm |
| `unknown` | Unavailable precipitation in route-day summaries |

`snow_day` is derived from snow observations and can be null when unavailable. Precipitation category alone does not identify snow. The existing prebuilt weather question selects `mod`/`heavy`, despite its snow-oriented label.

`mart_weather_impacts` averages route-day `pct_on_time` values per route/bin over the configured 30-day window. It subtracts that route's dry (`none`) average to form `delta_pct_on_time`. A delta of -0.15 means 15 percentage points lower than the dry baseline, not a 15% relative drop. Unknown days are excluded; absent dry observations yield a null baseline/delta. The averages weight route-day rows equally rather than by event count and establish association, not causation.

## Safety

`crash_100m_cnt` and `crash_250m_cnt` count crashes within those distances of a stop. The window runs from the latest staged crash date minus 365 days through that date, inclusively. `as_of_date` is the latest crash date, not automatically today's date; `window_days` is 365.

`severe_*_cnt` includes severity 3 **and** 4 (serious and fatal); `fatal_*_cnt` includes severity 4 only. These counts are geographic exposure indicators, not the number of transit-caused crashes or a per-passenger risk rate. A crash can count for several nearby stops.

`crash_score_0_100` min–max normalizes 250 m crash counts across stops. Larger means more exposure. Equal minimum and maximum can produce null scores through the denominator guard.

## Vulnerability

The model finds Denver tracts whose geometry lies within 804.672 m of a stop. It weights each matching tract's household-no-vehicle, transit-commuting, and poverty shares by **the whole tract's population**, then averages those three weighted indicators and min–max normalizes the result.

Fields are `pct_hh_no_vehicle_w`, `pct_transit_commute_w`, `pct_poverty_w`, and `vuln_score_0_100`. This is not population clipped to a walking catchment or a survey of riders using that stop. Larger scores mean more vulnerability relative to other observed stops; missing data can remain null. If all non-null raw values are equal, the implementation assigns 100 rather than a middle score.

## Sidewalk access

`sidewalk_len_m_within_200m` sums line length intersecting a 200 m stop buffer; `buffer_m` is 200. The model min–max normalizes this to `access_score_0_100`, rounded to one decimal place. Larger means more recorded nearby sidewalk length. No matched segment contributes zero; inventory gaps can therefore look like low access. If all lengths are equal, the implementation assigns 100.

This is not a connected walking route, crossing-safety score, wheelchair-accessibility certification, or on-the-ground condition inspection.

## Priority ranking

Despite its name, `reliability_score_0_100` measures **unreliability**: `100 * (1 - AVG(pct_on_time))` across stop-hour rows in the last 35 days. Larger is worse. Hours are averaged equally, not weighted by their event counts; hours without a known delay are skipped.

`priority_score = 0.5 * vulnerability + 0.3 * crash exposure + 0.2 * unreliability`.

The formula substitutes zero for missing component scores. Missing coverage can therefore reduce apparent priority; zero does not establish low need. `priority_rank` is a descending dense rank: 1 is highest priority, ties share a rank, and the next distinct score gets the next rank. Weights are project choices, not a validated official allocation rule.

## Dates, provenance, and reference tables

`service_date_mst` and `event_hour_mst` use `America/Denver`, including daylight saving time despite the historical suffix. Stop-visit service dates are GTFS service dates (`start_date`), so a trip running past midnight counts on the day it began; legacy partitions used the Denver date of the poll. `build_run_at` records model rebuilding, not newest underlying observation.

`mart_gtfs_stops` provides stop ID/name/lat/lon; `mart_gtfs_routes` provides route ID/name/long name/type. They support result enrichment and are not performance metrics.

For exact definitions, use [SQL model links](../../dbt/models/README.md). For sources/vintages, use [data coverage](DATA_SOURCES.md).
