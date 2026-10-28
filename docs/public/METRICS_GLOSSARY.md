# Metrics glossary

These definitions describe current SQL behavior. Fractions are normally 0–1, scores 0–100, delays seconds, distances meters, precipitation/snow mm, and temperatures Celsius. Inspect SQL and observation coverage before comparing values across engines/dates.

## Reliability

| Field | Current calculation and meaning |
|---|---|
| `n_events` | Count of resolved/sampled events in a group, not scheduled arrivals or passenger journeys |
| `n_reported_events` | Route-day count where resolved raw delay is non-null; compare with `n_events` to assess delay availability |
| `pct_on_time` | Mean of `ABS(delay_sec) <= on_time_sec`; default threshold 300 seconds. More than five minutes early is also off-time. |
| `mean_delay_sec` | Mean resolved delay; negative means early |
| `median_delay_sec`, `p90_delay_sec` | Approximate 50th/90th delay quantiles (route-day; stop-hour has p90) |
| `headway_adherence_rate` | Share of matched observed headways meeting schedule-match and headway-tolerance conditions |
| `obs_headway_sec_p50`, `obs_headway_sec_p90` | Approximate observed vehicle-spacing quantiles in stop-hour groups |
| `route_id_mode` | Most frequently observed assigned route in a stop/date/hour group; it is not a complete route breakdown |

**Missing-delay caveat:** `fct_trip_observation` uses the reported arrival delay, otherwise the reported departure delay, otherwise event time minus the scheduled time for the same trip, stop, and date, otherwise zero. A delay still missing after that counts as on-time. Until the October 27, 2026 rebuild the schedule table was stale, so January and April–August 2026 showed about 100% on-time; the rebuild recomputed all history since October 23, 2025 with the schedule current on each date (about 77% on-time in those months). This is not a census of verified physical arrivals. Staging selects one row per `(feed_ts_utc, trip_id)`, so feed coverage and selection affect every aggregate.

Observed headways are computed between selected event timestamps by route/direction/stop/date. The nearest scheduled headway is acceptable when its timestamp is within 1,800 seconds by default and the headway differs by no more than 50% of a positive scheduled headway. A missing match is not automatically an on-time vehicle. Headway measures describe available observations, not guaranteed complete service intervals.

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

Despite its name, `reliability_score_0_100` measures **unreliability**: `100 * (1 - AVG(pct_on_time))` across stop-hour rows in the last 35 days. Larger is worse. Hours are averaged equally, not weighted by their event counts.

`priority_score = 0.5 * vulnerability + 0.3 * crash exposure + 0.2 * unreliability`.

The formula substitutes zero for missing component scores. Missing coverage can therefore reduce apparent priority; zero does not establish low need. `priority_rank` is a descending dense rank: 1 is highest priority, ties share a rank, and the next distinct score gets the next rank. Weights are project choices, not a validated official allocation rule.

## Dates, provenance, and reference tables

`service_date_mst` and `event_hour_mst` use `America/Denver`, including daylight saving time despite the historical suffix. Current realtime service dates derive from event local dates, which can differ from GTFS operational service-day conventions after midnight. `build_run_at` records model rebuilding, not newest underlying observation.

`mart_gtfs_stops` provides stop ID/name/lat/lon; `mart_gtfs_routes` provides route ID/name/long name/type. They support result enrichment and are not performance metrics.

For exact definitions, use [SQL model links](../../dbt/models/README.md). For sources/vintages, use [data coverage](DATA_SOURCES.md).
