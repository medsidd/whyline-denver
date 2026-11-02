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

`snow_day` is derived from snow observations and can be null when unavailable. Precipitation category alone does not identify snow. The ready-made snow question compares each route's on-time share on snow days (`snow_day` true) with other days over the last year, for routes with at least three snow days.

`mart_weather_impacts` averages route-day `pct_on_time` values per route/bin over the configured 30-day window. It subtracts that route's dry (`none`) average to form `delta_pct_on_time`. A delta of -0.15 means 15 percentage points lower than the dry baseline, not a 15% relative drop. Unknown days are excluded; absent dry observations yield a null baseline/delta. The averages weight route-day rows equally rather than by event count and establish association, not causation.

## Safety

`crash_100m_cnt` and `crash_250m_cnt` count crashes within those distances of a stop. The window runs from the latest staged crash date minus 365 days through that date, inclusively. `as_of_date` is the latest crash date, not automatically today's date; `window_days` is 365.

`severe_*_cnt` includes severity 3 **and** 4 (serious and fatal); `fatal_*_cnt` includes severity 4 only. These counts are geographic exposure indicators, not the number of transit-caused crashes or a per-passenger risk rate. A crash can count for several nearby stops.

`ped_crash_250m_cnt` and `bike_crash_250m_cnt` count the 250 m crashes that involved a pedestrian or a cyclist; `ped_bike_severe_250m_cnt` counts those with a serious injury or a death. These are the crashes riders walking or cycling to the stop are exposed to.

`crash_score_0_100` min–max normalizes 250 m crash counts across stops. Larger means more exposure. Equal minimum and maximum can produce null scores through the denominator guard.

## Vulnerability

The model finds Denver tracts whose geometry lies within 804.672 m of a stop. It weights each matching tract's household-no-vehicle, transit-commuting, and poverty shares by **the whole tract's population**, then averages those three weighted indicators and min–max normalizes the result.

Fields are `pct_hh_no_vehicle_w`, `pct_transit_commute_w`, `pct_poverty_w`, and `vuln_score_0_100`. This is not population clipped to a walking catchment or a survey of riders using that stop. Larger scores mean more vulnerability relative to other observed stops; missing data can remain null. If all non-null raw values are equal, the implementation assigns 100 rather than a middle score.

## Sidewalk access

`sidewalk_len_m_within_200m` sums line length intersecting a 200 m stop buffer; `buffer_m` is 200. The model min–max normalizes this to `access_score_0_100`, rounded to one decimal place. Larger means more recorded nearby sidewalk length. No matched segment contributes zero; inventory gaps can therefore look like low access. If all lengths are equal, the implementation assigns 100.

`crosswalk_len_m_within_200m` is the part of that length Denver's inventory classes as crosswalk: a rough measure of marked crossings near the stop. `wheelchair_boarding` is RTD's GTFS flag (1 accessible, 2 not accessible, 0 no information).

This is not a connected walking route, crossing-safety score, wheelchair-accessibility certification, or on-the-ground condition inspection. The sidewalk inventory covers the City and County of Denver only, so stops elsewhere show no sidewalk or crosswalk.

## Priority ranking

Despite its name, `reliability_score_0_100` measures **unreliability**: `100 * (1 - AVG(pct_on_time))` across stop-hour rows in the last 35 days. Larger is worse. Hours are averaged equally, not weighted by their event counts.

`priority_score = 0.5 * vulnerability + 0.3 * crash exposure + 0.2 * unreliability`.

The formula substitutes zero for missing component scores. Missing coverage can therefore reduce apparent priority; zero does not establish low need. `priority_rank` is a descending dense rank: 1 is highest priority, ties share a rank, and the next distinct score gets the next rank. Weights are project choices, not a validated official allocation rule.

## Scheduled service

These describe the **published schedule**, not the service that ran. Each nightly build samples the next Wednesday (as `weekday`), Saturday and Sunday in the schedule. If a holiday falls on a sample date, its holiday service shows.

| Field | Meaning |
|---|---|
| `n_departures`, `avg_headway_min` (stop × route × direction × hour) | Scheduled departures in a local clock hour, and 60 divided by that count. Trips after midnight count in hours 0–3 of their service day. |
| `busiest_stop_id` | The stop with the most scheduled departures for the route, direction and day. Route frequency is measured there, so short-turn trips count. |
| `first_departure`, `last_departure`, `span_hours` | First and last scheduled departure at the busiest stop (local HH:MM) and the hours between them. |
| `headway_am_peak_min`, `headway_midday_min`, `headway_pm_peak_min`, `headway_evening_min` | Average minutes between departures over 7:00–8:59, 9:00–14:59, 15:00–17:59 and 18:00–20:59. NULL when nothing runs in that period. |
| `min_departures_per_3h`, `is_frequent_day` | Fewest departures in any three-hour block from 6:00 to 21:00, and whether that's at least 12. Twelve means every 15 minutes or better on average. Blocks are used rather than clock hours, so a departure slipping past the hour doesn't count against a 15-minute route. |
| `is_frequent_route` | `is_frequent_day` in every direction on all three day types: TransitCenter's frequent-network standard of 15 minutes or better, all day, every day. |
| `weekday_departures_share`, `weekday_departures_per_1000_residents` (tract) | Each stop's sample-Wednesday departures are shared among the tracts within 804.672 m by population, the same weights as `bridge_stop_tract`. Summed over tracts this equals the network total. Divided by tract population per 1,000. |
| `n_frequent_stops_nearby` | Stops within 804.672 m with at least 4 departures in every hour from 9:00 to 14:59. |

Limits:
- The schedule is what RTD planned. Missed trips and late running don't change these numbers.
- The frequency test is strict. Many routes run every 15 minutes at midday but every 20–30 minutes in the evening or at weekends, so they are frequent on some day types only. `is_frequent_day` and the period headways show that.
- Service per resident favours dense tracts near busy corridors and says nothing about where the service goes.

## Arrival-prediction accuracy

These compare the arrival time RTD's realtime feed predicted with when the vehicle actually reached the stop. For each stop visit measured from a shape crossing to within 30 seconds, the prediction "on screen" at 1, 3, 5, 10, 15, 20 and 30 minutes before the arrival is the latest prediction the feed had published by then. Each of those moments counts once, so a route's numbers weight every measured visit equally. The error is **actual minus predicted**: positive means the vehicle came later than predicted (a longer wait), negative means earlier (a rider trusting the prediction could miss it).

| Field | Meaning |
|---|---|
| `horizon_bucket` | The countdown the prediction showed: `0-3`, `3-6`, `6-12` or `12-30` minutes. A prediction already past its time ("due") counts as `0-3`; one showing more than 30 minutes counts as `12-30`, so early arrivals aren't dropped. With no prediction on screen, the bucket is the true time to arrival. |
| `n_predictions`, `n_no_prediction` | Visit-horizons with a prediction on screen, and those with none: nothing predicted yet, the stop dropped from the trip's predictions, or the stop marked skipped. |
| `pct_within_band` | Share of predictions counted accurate under the [MBTA's published standard](https://www.mbta.com/performance-metrics/arrival-prediction-accuracy): the vehicle came from 1 minute early to 1 minute late at 0–3 minutes, 1.5 early to 2 late at 3–6, 2.5 early to 3.5 late at 6–12, and 4 early to 6 late at 12–30. The bands allow more lateness than earliness, because an early vehicle can be missed. We found no RTD standard for prediction accuracy. |
| `median_error_sec`, `p05_error_sec`, `p95_error_sec` | The middle, 5th and 95th percentiles of the error (approximate quantiles). |
| `padding_sec` | How many seconds before the predicted time a rider must be at the stop to catch 95% of vehicles: `−p05_error_sec`, or 0 when vehicles rarely come early. |
| `pct_later_by_2min`, `pct_earlier_by_1min` | Share of predictions where the vehicle came more than 2 minutes late or more than 1 minute early. |

Limits:
- Only visits with a precisely measured arrival count; stops timed from the last prediction are excluded, since they would compare the prediction with itself.
- The poller reads the feed every 15 seconds, so a prediction that changed between polls is seen up to 15 seconds late. Apps that cache or smooth predictions may show riders something different.
- The first data starts on 2026-10-29, when the continuous stream started.

## Crowding

RTD's vehicles report how full they are as one of five levels, which WhyLine orders: 1 many seats available (or empty), 2 few seats available, 3 standing room only, 4 crushed standing room only, 5 full. "No data available" counts as no data. Each report counts toward the stop the vehicle is heading to or stopped at, so a stop's level is the highest reported on the way there.

| Field | Meaning |
|---|---|
| `n_trips`, `n_trips_with_data`, `pct_trips_with_data` (route × hour) | Trips the realtime stream tracked, those with at least one occupancy report, and the share. The hour is when the trip left its first stop. |
| `pct_trips_few_seats_or_worse`, `pct_trips_standing_or_worse` | Of trips with data, the share that reached that level anywhere on the trip. |
| `peak_stop_id_mode` | The stop where trips with few seats or worse most often first hit their highest level: the usual load point. |
| `n_visits`, `n_visits_with_data`, `pct_few_seats_or_worse`, `pct_standing_or_worse` (stop × hour) | The same at one stop, over the last 28 complete service dates, split by weekday or weekend. |

Limits:
- Only some vehicles report occupancy, and RTD sets the thresholds for each level. Always read a share with its coverage: on 2026-10-30, 88% of tracked trips and 81% of stop visits had data.
- The level is the highest reported, not the average. One crowded stretch makes a trip count as crowded.
- Holidays are counted as weekdays or weekends by their date.

## Missed trips

These follow every trip in the published schedule and ask whether a vehicle ran it. Each scheduled trip gets one outcome from what the realtime stream saw:

| Outcome | Meaning |
|---|---|
| `n_delivered` | A vehicle reported on the trip and it reached at least one stop. |
| `n_canceled` | RTD marked the trip canceled in its realtime feed. |
| `n_no_vehicle` | The trip was listed with predictions, but no vehicle ever reported on it. This is the usual sign of a "ghost bus". |
| `n_vehicle_no_visits` | A vehicle reported on the trip but it reached no stop. |
| `n_not_tracked` | The trip never appeared in either realtime feed. |

| Field | Meaning |
|---|---|
| `period` | When the trip was scheduled to leave its first stop: `early` 4:00–6:59, `am_peak` 7:00–8:59, `midday` 9:00–14:59, `pm_peak` 15:00–17:59, `evening` 18:00–20:59, `night` 21:00–3:59. |
| `n_observable`, `stream_healthy` | Trips whose whole run, from 10 minutes before the scheduled start, fell in 15-minute windows with at least 24 of the feed's roughly 30 updates. `stream_healthy` means every trip in the row was observable. |
| `pct_delivered`, `pct_missed_likely` | Of observable trips, the delivered share, and the canceled, no-vehicle and not-tracked share. |
| `pct_tracked_with_vehicle` | Over 28 service dates, the share of the route's tracked, uncanceled trips with a vehicle report. Below 0.8, the route's vehicles rarely report, and both shares are NULL. |

Limits:
- "Likely missed" is inferred from the data RTD publishes. A trip can run with its tracking unit off, and that looks the same as a trip that didn't run.
- The N Line is withheld: on 2026-10-30 only 3 of its trains reported positions, so most of its trips had no vehicle.
- A late trip still counts as delivered; lateness is in the reliability metrics.

## Wait time, bunching and gaps

For frequent service, riders turn up without checking a timetable, so what matters is how evenly vehicles are spaced. A headway is the time between one vehicle of a route and direction reaching a stop and the next one reaching it.

| Field | Meaning |
|---|---|
| `expected_wait_sec` | Average wait for a rider arriving at random: the sum of squared observed headways divided by twice their sum. Uneven spacing raises it even when the number of vehicles is right. |
| `scheduled_wait_sec`, `excess_wait_sec` | The same calculation over the scheduled headways, and the difference: the extra waiting caused by bunching, gaps and missed trips. |
| `pct_bunched`, `pct_gap` | Share of headways under a quarter of the scheduled headway, and over one and a half times it. |
| `service_class` (stop) | `frequent` when scheduled every 15 minutes or better on average in that stop, route, direction, day type and period; else `infrequent`. The route-day mart uses only headways scheduled every 15 minutes or better for wait, bunching and gaps. |
| `pct_on_time`, `p90_delay_sec` | Share of visits from 1 minute early to 5 minutes late (RTD's window), and the 90th percentile delay. For infrequent service, read these instead of wait. |

Limits:
- A trip that ran without being seen at the stop makes a false gap. Visits timed from the last prediction count only when a vehicle reported on the trip, so a ghost trip leaves the gap riders saw, but a vehicle that was never seen at all looks like one.
- Each headway belongs to the period when the later vehicle arrived. The first vehicle of the day has no headway.
- Holidays are counted by their date, as weekdays, Saturdays or Sundays.

## Speed and travel time

A segment runs from one stop of a trip to the next. Its running time is from leaving the first stop to reaching the second, with both ends measured to within 30 seconds; dwell at the stops is excluded. Distance is along the route's shape.

| Field | Meaning |
|---|---|
| `p50_speed_kmh`, `p10_speed_kmh` | Median and 10th percentile speed between the two stops, by route, direction, day type and hour, over 28 days. |
| `p50_travel_sec`, `p90_travel_sec`, `scheduled_travel_sec`, `delay_ratio` | Median and 90th percentile running time, the median scheduled time, and median over scheduled. The ratio is NULL when the schedule gives both stops the same minute. |
| `lat`, `lon` (segment) | The midpoint between the two stops. |
| `p50_runtime_min`, `p90_runtime_min`, `scheduled_runtime_min` | End-to-end run time from leaving the first stop to reaching the last, per route, direction, first and last stop, and day. |
| `buffer_time_index` | `(p90 − p50) / p50`: the extra share of time to allow to arrive on time nine times in ten. 0.2 means allowing 20% more than the typical trip. |

Limits:
- Segments only count when both stops were timed to within 30 seconds, so rail, which reports less often, has fewer segments.
- Speeds over 130 km/h, faster than any RTD vehicle, are timing error on closely spaced stops and are dropped.
- The day's buffer time index mixes peak and off-peak trips.




## Ridership

From the National Transit Database, which RTD reports to the Federal Transit Administration monthly; figures run about two months behind and FTA revises earlier months.

| Field | Meaning |
|---|---|
| `boardings` | Unlinked passenger trips by mode and month: every boarding counts, so a ride with one transfer counts twice. Directly operated and purchased service are added together. |
| `revenue_hours`, `revenue_miles`, `peak_vehicles` | Hours and miles vehicles spent in passenger service, and vehicles in maximum service. |
| `boardings_per_revenue_hour` | Boardings per hour of service: how productive each hour is. |
| `boardings_year_earlier`, `boardings_yoy_change` | The same month a year before, and the relative change (0.05 is 5% more). |

## Weather in the hour

`mart_weather_impacts_hourly` matches each stop visit with the weather in the hour the vehicle reached the stop, rather than the day's totals. Levels: precipitation `none` (under 0.1 mm in the hour), `light` (under 1 mm), `moderate` (under 4 mm), `heavy`; snowfall `snowing` or `not_snowing`; temperature `below_-10`, `-10_to_0`, `0_to_30`, `30_plus` (°C). `delta_pct_on_time` is the on-time share at that level minus the route's share when dry, not snowing, or 0–30 °C.

Limits: hourly weather is modelled by Open-Meteo at Denver International Airport, and recent hours are forecast-model values until the archive catches up. It starts on 2026-10-23, so visits before then aren't matched. Few hours have heavy weather, so shares at those levels are noisy, and other things (time of day, events) vary with weather; this shows association, not cause.

## Dates, provenance, and reference tables

`service_date_mst` and `event_hour_mst` use `America/Denver`, including daylight saving time despite the historical suffix. Current realtime service dates derive from event local dates, which can differ from GTFS operational service-day conventions after midnight. `build_run_at` records model rebuilding, not newest underlying observation.

`mart_gtfs_stops` provides stop ID/name/lat/lon; `mart_gtfs_routes` provides route ID/name/long name/type. They support result enrichment and are not performance metrics.

For exact definitions, use [SQL model links](../../dbt/models/README.md). For sources/vintages, use [data coverage](DATA_SOURCES.md).
