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

Every visit keeps `arrival_earliest_ts` and `arrival_latest_ts`, so its own uncertainty travels with it. A stop's arrival point is the stop pole's distance along the shape, or the first STOPPED_AT report at that stop when the vehicle stopped short of the pole. Interpolation assumes constant speed between the two reports, so it slightly favours early estimates for a bus decelerating into the stop; the dual run measures that bias against STOPPED_AT reports. Reports are used only when they are fresh (at most 120 s old), inside the bounding box around RTD's network and within 100 m of the shape; detours and layovers therefore leave gaps. Trains report less often than buses (light rail p90 gap 76 s), so rail windows are wider. In a 20-minute sample on October 28, 2026, 85% of bus visits fell within 30 s, against 25% for light rail and 30% for commuter rail. RTD's canceled trips get no visits; they appear in `fct_trip_status` with outcome `canceled`.

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

Appended columns: route-day `data_version`, `n_skipped`, `n_canceled_trips`, `n_scheduled`, `pct_observed`, `pct_shape_crossing`, `pct_last_prediction`, `pct_within_30s`, `median_window_sec`; stop-hour `data_version`, `n_reported_events`, `pct_within_30s`, `pct_shape_crossing`. `mart_weather_impacts` and the priority ranking's unreliability score read `pct_on_time`, so they change too; both read stop-visit days only, so their 30- and 35-day windows fill up over the month after the cutover. Service dates before 2026-10-29 keep the legacy method: the stream began late on October 28's service day, with only 107 visits.

**What it does to the numbers.** Fleet on-time falls from 88–92% before the cutover to 74–77% after, and 119 of 120 routes go down. About 12 of the 14 points come from counting arrivals more than a minute early as not on time; the rest from timing every stop instead of sampled terminal arrivals, and from no longer counting unknown delays as on time. Don't compare `pct_on_time` across `data_version`, or average a window that spans both: filter `data_version IS NOT NULL` for the stop-visit method. Bus also runs below RTD's own figure: 73.9% from October 30 to November 5, against 81–85% in every month RTD reported from January 2025 to August 2026 (83.3% in August). The gap comes from how each counts, not from missing visits. RTD doesn't publish its full rules, but three common agency conventions, applied to the same visits, reach 81.2%: timing only RTD's timepoints, by departure where the vehicle was seen standing (74.7%); counting up to 5 minutes 59 seconds late as on time (78.5%); and not counting early arrivals at a trip's last stop (81.2%). WhyLine keeps its stricter rule, because it describes every stop a rider uses. See [RTD's reported on-time performance](#rtds-reported-on-time-performance). Rail is close to RTD's figures. Routes that run ahead of schedule score lowest: the AL reaches its last stop a median 10 minutes early, and the 16th Street FreeRide (`FREE`) leaves stops early with buses minutes apart, so its riders rarely wait long. [Wait time](#wait-time-bunching-and-gaps) describes the FreeRide better. Details are in the [dual-run review](../technical/OPERATIONS.md#dual-run-review-november-5-2026-utc).

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

`snow_day` is derived from snow observations and can be null when unavailable. Precipitation category alone does not identify snow. The ready-made snow question compares each route's on-time share on snow days (`snow_day` true) with other days over the last year, for routes with at least three snow days. It compares within one method at a time (`method` is `sampled` for partitions before the cutover, otherwise `data_version`), so a route can appear once per method; every snow day so far predates the cutover.

`mart_reliability_by_route_day` also carries the day's `precip_mm`, `snow_mm`, `tmin_c` and `tmax_c`, plus `temp_band` on the mean of the low and high: below −10 °C, −10 to 0, 0 to 30, and 30 °C and above. They're NULL on partitions from before the cutover, which can't be rebuilt. For on-time by temperature, `mart_weather_impacts_hourly` uses the temperature in the hour of each visit.

`mart_weather_impacts` averages route-day `pct_on_time` values per route/bin over the configured 30-day window, using stop-visit days only so the change of method isn't read as a weather effect. It subtracts that route's dry (`none`) average to form `delta_pct_on_time`. A delta of -0.15 means 15 percentage points lower than the dry baseline, not a 15% relative drop. Unknown days are excluded; absent dry observations yield a null baseline/delta. The averages weight route-day rows equally rather than by event count and establish association, not causation.

## Safety

`crash_100m_cnt` and `crash_250m_cnt` count crashes within those distances of a stop, from Denver's latest crash extract (its five-year window; before 2026-11-03 older extracts were merged in, which counted crashes Denver had re-numbered twice). The window runs from the latest staged crash date minus 365 days through that date, inclusively. `as_of_date` is the latest crash date, not automatically today's date; `window_days` is 365.

`severe_*_cnt` includes severity 3 **and** 4 (serious and fatal); `fatal_*_cnt` includes severity 4 only. These counts are geographic exposure indicators, not the number of transit-caused crashes or a per-passenger risk rate. A crash can count for several nearby stops.

`ped_crash_250m_cnt` and `bike_crash_250m_cnt` count the 250 m crashes that involved a pedestrian or a cyclist; `ped_bike_severe_250m_cnt` counts those with a serious injury or a death. These are the crashes riders walking or cycling to the stop are exposed to.

`crash_score_0_100` min–max normalizes 250 m crash counts across stops. Larger means more exposure. Equal minimum and maximum can produce null scores through the denominator guard.

## Walking to the stop

`mart_stop_walk_safety` describes the street around each stop inside Denver from the city's open-data layers, refreshed weekly:

| Field | Meaning |
|---|---|
| `on_hin`, `hin_tier` | A High Injury Network street (Denver's streets with the most serious and fatal crashes) is within 30 m; tier 1 streets have the highest crash rates. |
| `nearest_signal_m` | Meters to the nearest traffic signal, a proxy for a controlled crossing; NULL beyond 1 km. |
| `n_curb_ramps_50m` | Curb ramps in the city's inventory within 50 m. |
| `existing_bikeway_within_100m`, `on_transit_lane`, `transit_signal_priority_within_50m`, `queue_jump_within_50m` | Bike and bus infrastructure next to the stop. |
| `frontage_m_100m` | Street frontage in Denver's sidewalk asset inventory within 100 m, with or without sidewalk: every side of every street, so a corner stop has more. The base for the three shares below. |
| `pct_frontage_no_sidewalk_100m` | Share of that frontage with no sidewalk (the inventory's "Missing Sidewalk"). |
| `pct_sidewalk_under_5ft_100m` | Share of the existing sidewalk narrower than 5 feet, the width Denver's sidewalk plan treats as deficient. |
| `pct_sidewalk_fair_or_poor_100m` | Share of the existing sidewalk rated fair or poor in the city's 2022 baseline survey. |
| `walk_safety_flags` | Plain-language flags: on the High Injury Network with no signal within 100 m; on a tier 1 street; no curb ramp recorded within 50 m; no sidewalk on a quarter or more of the street frontage within 100 m. |

Limits: the layers cover the City and County of Denver only, so other stops are left out rather than shown as safe. Inventories can lag construction, and a signal isn't always a marked crosswalk at the stop. Sidewalk lengths are measured inside a 100 m circle, not along a walking route; width is recorded in whole feet, and condition dates from 2022 unless the city has since updated a segment. Shares are NULL when nothing is inventoried within 100 m.

## Vulnerability

The model finds Denver tracts whose geometry lies within 804.672 m of a stop. It weights each matching tract's household-no-vehicle, transit-commuting, and poverty shares by **the whole tract's population**, then averages those three weighted indicators and min–max normalizes the result.

Fields are `pct_hh_no_vehicle_w`, `pct_transit_commute_w`, `pct_poverty_w`, and `vuln_score_0_100`. This is not population clipped to a walking catchment or a survey of riders using that stop. Larger scores mean more vulnerability relative to other observed stops; missing data can remain null. If all non-null raw values are equal, the implementation assigns 100 rather than a middle score.

## Equity layers

For stops inside Denver, `mart_vulnerability_by_stop` adds the measures of the block group containing the stop:

| Field | Meaning |
|---|---|
| `enviroscreen_pctl` | Colorado EnviroScreen 2.0 percentile from the state health department (CDPHE): combined environmental, health and demographic burden, ranked within Colorado. Higher is more burdened. |
| `is_disproportionately_impacted`, `di_community_type` | Whether the block group is a disproportionately impacted community under Colorado law, and the reason CDPHE gives. |
| `doti_equity_score`, `doti_equity_group_rank` | Denver DOTI's equity index: a score (16–68 in 2026; higher means more need) and a group from 1 (highest need) to 6. |

`mart_service_equity_by_group` compares service for stops in each group over 28 days: scheduled departures per stop per day, on-time share, excess wait at frequent stops, and the share of visits arriving with standing room only. Missed trips are counted per trip, not per stop, so they aren't split by group. The groups describe where stops are, not who rides; differences show association.

## Sidewalk access

`sidewalk_len_m_within_200m` sums line length intersecting a 200 m stop buffer; `buffer_m` is 200. The model min–max normalizes this to `access_score_0_100`, rounded to one decimal place. Larger means more recorded nearby sidewalk length. No matched segment contributes zero; inventory gaps can therefore look like low access. If all lengths are equal, the implementation assigns 100.

`crosswalk_len_m_within_200m` is the part of that length Denver's inventory classes as crosswalk: a rough measure of marked crossings near the stop. `wheelchair_boarding` is RTD's GTFS flag (1 accessible, 2 not accessible, 0 no information).

This is not a connected walking route, crossing-safety score, wheelchair-accessibility certification, or on-the-ground condition inspection. The sidewalk inventory covers the City and County of Denver only, so stops elsewhere show no sidewalk or crosswalk.

## Priority ranking

Despite its name, `reliability_score_0_100` measures **unreliability**: 100 × the share of measured stop visits (those with a known delay) that weren't on time over the last 35 days, from stop-visit dates only. Larger is worse. Each visit counts once, so busy hours weigh more than quiet ones. A stop needs at least 30 measured visits in the window for a score; below that it's NULL, because a few visits can't rank a stop. Six early arrivals at a downtown drop-off stop once ranked it first. The ready-made equity question lists only stops with a score.

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

## Bus lanes

`mart_transit_lane_speed_by_week` compares, week by week and by period, the median speed and delay ratio (running time over scheduled) on each Denver transit-lane corridor with the same routes' segments that have no lane. A segment counts as on the lane when at least half of the straight line between its stops lies within 15 m of the lane.

Limits:
- **No before-and-after yet.** Every lane in the city's layer was built by 2022, before WhyLine's timed data starts on 2026-10-28.
- **The comparison is confounded.** Lane segments are on busy downtown streets with closely spaced stops, so they're slower in km/h whatever the lane does. Compare delay ratios, and the change between midday and the peaks, rather than raw speed.
- **For a new lane:** set its opening date in the `lane_openings` variable, and `weeks_since_opening` counts the weeks before and after.

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




## Service alerts

From RTD's service alerts feed, snapshotted every 15 minutes since 2026-11-02. An alert names routes, stops or trips and gives periods when it applies.

| Field | Meaning |
|---|---|
| `from_ts`, `until_ts` (stop closures) | When the alert applies: its stated period, starting when it was first seen if none is given. Once the alert leaves the feed, it ends no later than 15 minutes after it was last seen, unless its period hadn't begun yet: RTD can stop listing a trip cancellation hours before the trip, so such a period keeps RTD's own end. An empty `until_ts` means it's open-ended and still listed. |
| `is_closure` | The alert's effect is `NO_SERVICE` or `STOP_MOVED`. Detours often close stops too, but RTD says so only in the alert text. |
| `is_active_now` | In the feed and within its period when the table was built (nightly). |
| `n_alerts`, `alert_hours`, `n_stops_named` (route × day × effect) | Alerts in effect on the route that day, the hours each was in effect summed over alerts (so two at once count twice), and stops named. |

Limits: alerts describe what RTD announced, not what happened. Alerts that ended before 2026-11-02 are missing. When RTD edits an alert's period, the last version wins.

## Scooters and bikes near stops

From Veo's public feed, Denver's only scooter and e-bike operator since May 2026, snapshotted every 15 minutes since 2026-11-02. A vehicle counts when it's neither reserved nor disabled.

| Field | Meaning |
|---|---|
| `avg_scooters_within_200m`, `avg_bikes_within_200m` | Average available vehicles within 200 m of the stop across the period's snapshots, over 28 days. Bikes include e-bikes and pedal bikes. |
| `pct_time_no_scooter`, `pct_time_no_bike` | Share of snapshots with none within 200 m: how often a rider would find nothing nearby. |

Limits: only stops inside the City and County of Denver, Veo's service area, are included. A vehicle shown as available may be hard to unlock or out of charge. Stops next to a Veo staging or charging site can show far more vehicles than a rider would usually find: W 10th Ave & Decatur St (stops 10038 and 25926) averaged about 34 scooters and 27 bikes at midday on 2026-11-02. Today's figures fill in through the day (`n_snapshots` shows hours still filling); the first day, 2026-11-02, starts at 10:49.

## RTD's reported on-time performance

`mart_reported_vs_measured_by_month` sets RTD's own monthly figures, from its Bus and Rail Operations reports, beside WhyLine's measured share for the same month and service (all bus, light rail, the A, B and G lines, the N Line).

The two are measured differently:
- RTD measures at timepoints, using its own rules and adjustments.
- WhyLine measures at every stop it can time, counting from 1 minute early to 5 minutes late.

For bus, the measured gap is 8–10 points, and those rule differences account for most of it ([cutover notes](#changed-definitions-at-the-cutover)). A gap between them is expected; a gap that changes over time is the more telling signal. Months overlap only once WhyLine has measured them (from 2026-10-28) and RTD has published them, about two months later. RTD's Local, Regional and Regional BRT figures need RTD's route classification and aren't compared yet.

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

## Jobs reachable by transit

`mart_job_access_by_tract` counts the jobs a resident of each tract can reach by walking and transit within 30, 45 and 60 minutes.
- **Coverage:** every tract in the RTD counties inside the RTD area.
- **Windows:** the next Tuesday at 7:00, 12:00 and 19:00, and the next Saturday at 10:00. Each is two hours, and the travel time is the median over it, so it reflects a typical, not lucky, departure.
- **Jobs:** U.S. Census LEHD (LODES) workplace counts, all jobs. `pct_region_jobs_45min` is the share of all routed jobs.
- **Stop scorecard:** it carries `jobs_within_45min_am_peak`, weighted over the Denver tracts near each stop.

Limits:
- **Schedule, not reality:** travel times come from the published schedule, not from what ran, so late or missed trips aren't reflected.
- **Approximation:** routing runs between tract centre points, which approximates longer walks in large tracts.
- **Privacy noise:** LODES adds noise to small job counts for privacy.
- **Refresh:** results refresh weekly with the schedule.

## Scorecards

`mart_stop_scorecard` (one row per stop) and `mart_route_scorecard` (one row per route, both directions) gather the measures above over the last 28 service dates, using the same definitions. Each measured part comes with the count it rests on (`n_visits_measured`, `n_visits_with_occupancy`, `n_trips_observable` and so on). A part with no data stays empty rather than zero, so a stop with no occupancy reports isn't shown as uncrowded.

## Live data

Two views answer questions about right now. They read the newest realtime load every time they're queried, so they **trail real time by 15–30 minutes**: the poller publishes a batch every 15 minutes and `realtime-load` loads it at :02, :17, :32 and :47. They aren't an arrivals board.

| View | What it holds |
|---|---|
| `mart_vehicles_now` | Vehicles running in the newest load: each vehicle's latest report from the last 45 minutes of feed time, kept when it is within 10 minutes of the newest report, so a bus that stopped reporting drops out with the next load. Route (NULL when the vehicle isn't on a trip), direction, trip, the stop it's at or heading to, position, speed, occupancy level, `report_ts_mst` and `minutes_ago`. |
| `mart_stop_visits_recent` | Stop visits from the last 2 hours, skipped stops included (by their scheduled arrival): route, stop, `arrival_ts_mst`, `delay_sec`, `delay_min` and `is_on_time` (the nightly marts' thresholds, RTD's rule by default; NULL when the delay is unknown). |

"Routes running now" counts routes with at least one vehicle on a trip in `mart_vehicles_now`. A route whose vehicles stopped reporting looks like it isn't running. The dashboard says when the newest vehicle report was made. The dashboard's date filter doesn't apply to these views, and they aren't in the nightly downloads or the DuckDB warehouse.

## Dates, provenance, and reference tables

`service_date_mst` and `event_hour_mst` use `America/Denver`, including daylight saving time despite the historical suffix. Stop-visit service dates are GTFS service dates (`start_date`), so a trip running past midnight counts on the day it began; legacy partitions used the Denver date of the poll. `build_run_at` records model rebuilding, not newest underlying observation.

`mart_gtfs_stops` provides stop ID/name/lat/lon; `mart_gtfs_routes` provides route ID/name/long name/type. They support result enrichment and are not performance metrics.

For exact definitions, use [SQL model links](../../dbt/models/README.md). For sources/vintages, use [data coverage](DATA_SOURCES.md).
