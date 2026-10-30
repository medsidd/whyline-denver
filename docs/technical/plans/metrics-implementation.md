# WhyLine Denver: implementation plan for the approved metrics

## Context

On 2026-10-30 the owner approved an 18-item metrics roadmap, built on research into what riders, advocates and planners need from transit data. They then approved this implementation plan. It splits the work into 16 work packages (WP), in execution order. Each work package has:
- the user question it answers;
- definitions;
- the files it touches;
- its output schema;
- its tests;
- owner actions;
- its cost;
- acceptance criteria.

Progress is recorded in [operations](../OPERATIONS.md).

One correction to the roadmap: **Denver's micromobility provider is now Veo.** Veo became the city's only operator under a three-year licence approved on April 27, 2026; it launched on May 1, and Lime's and Bird's agreements ended on May 16 ([Denverite](https://denverite.com/2026/04/15/denver-veo-scooter-contract-moves-forward/), [Denver Gazette](https://www.denvergazette.com/2026/04/28/goodbye-lime-and-bird-hello-veo-heres-what-you-need-to-know-about-denvers-new-scooters/), [city program page](https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Department-of-Transportation-and-Infrastructure/Programs-Services/Transit/Micromobility-Program)). I verified Veo's Denver feed on 2026-10-30:
- address: `https://cluster-prod.veoride.com/api/shares/name/den/gbfs` (GBFS 2.2);
- 8,411 vehicles, all inside Denver;
- vehicle types: e-bike 4,794, and three scooter types with 2,515, 1,075 and 27 vehicles; no dock stations.

The old Lyft feed has been frozen since about 2024, Bird's is empty, and Lime's address returns 404. Veo is the only feed used (WP14).

## Verified facts this plan relies on (2026-10-30)

| Fact | Evidence |
|---|---|
| RTD vehicle reports carry occupancy | On 2026-10-29: 73% of reports had a value: many seats 601,677; no data 245,708; few seats 46,741; standing room only 6,476; crushed standing room only 696; full 445. Speed is filled in for only about 3%; bearing for all. |
| RTD Alerts feed is live | `open-data.rtd-denver.com/files/gtfs-rt/rtd/Alerts.pb` (HTTP 200, 43 KB, 76 alerts). Effects: 38 no service, 26 detour. Causes: 48 construction. 273 informed entities name route and stop. Up to 365 active periods per alert. English only. |
| NTD monthly ridership API | Socrata dataset `8bui-9xvu` on data.transportation.gov. RTD is `ntd_id=80006`, with `upt`, `vrh`, `vrm` and `voms` by mode and month. |
| LODES | `lehd.ces.census.gov/data/lodes/LODES8/co/wac/co_wac_S000_JT00_2023.csv.gz` (2023 available), plus the `od` and `rac` files |
| Colorado EnviroScreen 2.0 | ArcGIS `services3.arcgis.com/66aUo8zsujfVXRIT/.../ColoradoEnviroScreen_v2_Tract_24118_Final/FeatureServer/0`: 178 Denver tracts (GEOID `08031…`), with `ES_S_` (EnviroScreen percentile) and component percentiles. The field codes are short; their aliases hold the full names. The block-group layer is `EJP_Main_English_v2_BlockGroup_71124_Final_view`. |
| Denver open-data layers, from the same ArcGIS org as the existing ingestors (`services1.arcgis.com/zdB7qR0BtYrg0Xpl`) | High Injury Network `ODC_TRANS_HIN_L/326` (496 lines; StreetName, CrashRate, Tier) · transit lanes `ODC_TRANS_TRANSITLANES_L/349` (24, with ROUTES and YEAR_BUILT) · transit signals `ODC_TRANS_TRANSITSIGNALS_P/350` (30, with TSP and queue jump) · curb ramps `ODC_TRANS_CURBRAMPS_P/228` (72,770) · traffic signals `ODC_TRANS_TRAFFICSIGNAL_P/147` (1,288) · bike facilities `Denver_Bicycle_Facilities_ODC/450` (2,025) · street centerlines `ODC_TRANS_STREET_L/145` (30,706, with FUNCLASS) · DOTI equity index `ODC_ADMN_DOTI_EQUITY_INDEX/151` (572 block groups) · pedestrian demand index `ODC_ADMN_PEDDEMANDINDEX_A/442` · snow routes `ODC_TRANS_SNOWROUTE_L/310` |
| Open-Meteo hourly | `archive-api.open-meteo.com/v1/archive?…&hourly=precipitation,snowfall,temperature_2m` works with no key |
| RTD monthly on-time reports | Bus and Rail Operations PDFs on `cdn.rtd-denver.com` with random suffixes (for example `Bus_Operations_April_2026_emliql.pdf`). No index page found yet. |
| RTD route boardings | Published only in a Power BI dashboard; no download |

## Shared rules

**Raw expiry.** The four raw stream tables keep 90 days, so the first data goes on about **2027-01-27**. Every fact that needs raw vehicle reports or prediction history (WP1, WP2, WP5) must be built and running before then. After that, history is only recoverable by replaying the Coldline archive.

**Build now, publish after validation.**
- The facts can run now, because `fct_stop_visit` and `fct_trip_status` refresh every 15 minutes.
- Marts that depend on visit timing (WP1, WP3, WP4, WP5) get `allow_in_app: false` until the November 5 dual-run review passes, and are switched on in the cutover PR or right after it.
- WP2 depends only on vehicle reports and could be published earlier; it still waits for its own coverage check.

**Avoid conflicts with #71.** #71 rewrites `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`, their `schema.yml` entries and the glossary. New work adds new models and new glossary sections and doesn't edit those two marts until #71 has merged. New models also:
- read the on-time window as `var('on_time_early_sec', 60)` and `var('on_time_late_sec', 300)`, with those defaults, since #71 replaces `on_time_sec` with them;
- never `ref()` `stg_rt_events`, `fct_trip_observation` or `fct_stop_arrival`, which #71 disables.

Whichever of a work package and #71 merges second rebases the README counts and the glossary.

**Checklist for a new source** (the pattern of the existing ingestors):
1. An ingestor in `src/whyline/ingest/<name>.py`. Copy `denver_crashes.py` for ArcGIS layers (`fetch_features` paging and `normalize_records`) or `noaa_daily.py` for HTTP JSON. Each writes `raw/<name>/extract_date=<d>/<file>.csv.gz` (snapshot sources) or `raw/<name>/snapshot_at=<YYYY-MM-DDTHH:MM>/…` (intraday sources) through the per-ingestor gzip, manifest and `io.write_manifest` helpers, and skips if the output exists.
2. A `JobSpec` in `src/whyline/load/registry.py` whose column order equals the CSV order, with partitioning (and expiry where the data is intraday).
3. A Makefile target added to `ingest-static`. Use the non-fatal `-$(MAKE)` form for optional sources, and add it to `ingest-all` and `.PHONY`. If a key is needed, add an env line to `.github/workflows/nightly-ingest.yml`.
4. Refresh cadence: reference layers that rarely change skip the download when an extract from the last 7 days exists, so daily runs don't pile up copies.
5. A dbt source in `dbt/models/sources_raw.yml` with a bounded freshness filter. A staging view that dedupes on the latest `_ingested_at` per natural key, as `stg_weather` does, with tests.
6. Tests:
   - an ingestor unit test with HTTP monkeypatched, as `tests/ingest/test_noaa_daily.py` does;
   - a fixture under `tests/fixtures/<name>/`;
   - an entry in `tests/ingest/test_contracts.py` and `test_manifests.py`.
7. Docs: `docs/public/DATA_SOURCES.md`, `docs/contracts/CONTRACTS.md`, the attribution page (`frontend/src/app/attribution/page.tsx`) with the source's terms, and counts in `AGENTS.md` and the model README.

**Checklist for a new mart.** This follows `docs/technical/guides/ADDING_A_MART.md`, with the gaps the code inventory found:
1. **Model SQL**: `config(materialized=…, meta={"allow_in_app": <bool>}, …)`. App exposure is set in this `meta` and in `ALLOWLISTED_MARTS`, not in `schema.yml`.
   - Date-grained marts are incremental `insert_overwrite`, partitioned on a column named **`service_date_mst`**, with a TIMESTAMP **`build_run_at`**. The exporter and the guardrail's partition check expect those names; for visit-based marts the column holds the GTFS service date, the same meaning as after #71.
   - Set `full_refresh=false` where history can't be rebuilt.
   - Rolling snapshot marts are tables.
2. **`dbt/models/marts/schema.yml`**: description, plain-language column descriptions and tests.
3. **Serving lists:**
   - `src/whyline/sync/constants.py` `ALLOWLISTED_MARTS`;
   - `src/whyline/sync/export_bq_marts.py` `PARTITIONED_MARTS` (date-grained marts only; everything else exports as a daily snapshot);
   - `src/whyline/sync/refresh_duckdb.py` `HOT_MARTS`, plus `LATEST_RUN_DATE_ONLY_MARTS` for snapshot marts;
   - `api/routers/downloads.py` `MART_OPTIONS` and its mirror in `frontend/src/components/ui/DownloadPanel.tsx`;
   - if the LLM needs a hint, a rule in `src/whyline/llm.py`'s prompt.
4. **Docs:**
   - a glossary section in `docs/public/METRICS_GLOSSARY.md` (definition, formula, limits);
   - counts in `dbt/models/README.md` (lines 3, 14, the mart table, bus matrix and mart fields), `AGENTS.md:41-42`, `docs/QA_Validation_Guide.md:118`, `docs/technical/FRONTEND.md:13` and `docs/technical/API_REFERENCE.md:58`;
   - a node and edges in `docs/diagrams/data_model_overview.mmd` (hand-maintained);
   - `dbt/models/exposures.yml`.
5. **Test:** a DuckDB-rendered SQL test. WP0 adds a shared `tests/sql/_render.py`, holding the Jinja stubs and dialect replacements that each file now inlines; it's a new file, so it can't conflict with #71. Spatial joins run in BigQuery GIS. The DuckDB tests use a small `st_dwithin` macro over latitude and longitude, using haversine distance, because the existing tests don't load DuckDB's spatial extension.
6. **Ready-made question:** `api/routers/sql.py` `PREBUILT` (list position is the id, and the docstring says 0–3), `frontend/src/types/api.ts` `PREBUILT_QUERIES`, and the docs. WP0 makes `CHIP_COLORS` in `PrebuiltQuestions.tsx` cycle, because a fifth question would crash it today.
7. **Release:** the API reads `dbt/target` baked into its image, and caches the models. A new mart therefore reaches the app only after the artifacts are regenerated and committed, the API image is rebuilt and the service is redeployed. That's bundled into releases R1–R4 (below).

**Cost.** The realtime job already uses most of its 460 MiB budget per 15-minute run, so every new model runs **nightly** (`staging core marts` picks them up automatically). Each PR reports dry-run bytes. Expected nightly additions are given per work package.

**Delivery.** One PR per work package, merged after `make test`, `make lint`, `make test-ingest`, `dbt parse` and `compile`, dry runs, a DuckDB test, and CI pass, under your standing permission.

**Owner actions** are listed per work package. These are cloud steps my permission check blocks: job image updates, scheduler changes, IAM.

---

## WP0: quick fixes and usage telemetry (item 9)

- **Snow question:** the ready-made "Where snow hurts" question queries `mart_weather_impacts`, which has no `snow_day` column. It ranks moderate and heavy precipitation, and a route can appear twice. Rewrite it on `mart_reliability_by_route_day`, comparing snow days with other days for each route. Also correct the four docs that note the flaw: the glossary (line 32), `API_REFERENCE.md:58`, `QA_Validation_Guide.md:120` and the public FAQ (line 21).
- **`route_bar` chart:** `chartLogic.ts` and `Step3Results.tsx:191-199` need `avg_delay_ratio`, which no mart produces. Switch the rule and the chart to `route_id` plus `pct_on_time` or `p90_delay_sec`. Also give the "heatmap" type a real stop × hour grid; today it draws a bar chart of the first 15 rows.
- **Ready-made question chips:** make `CHIP_COLORS` in `PrebuiltQuestions.tsx` cycle with `i % length`. In `page.tsx`, the four-item limits are the `TOPICS`, the `MAP_LINES` paths, the hero aria-label and the "Four topics" line; make them follow the length of `TOPICS` so WP15 can add topic cards.
- **Shared SQL-test helper:** add `tests/sql/_render.py` (see the new-mart checklist).
- **Weather mart:** add `tmin_c`, `tmax_c`, `snow_mm` and `precip_mm` from `fct_weather_daily`, plus `temp_band` (below −10 °C, −10 to 0, 0 to 30, 30 °C and above). Add a `mart_weather_impacts` view by temperature band. This changes `mart_reliability_by_route_day`, which #71 also edits, so it's done **after #71 merges**.
- **Query log bug** (`api/routers/query.py:97-106`): `models=list(allowlist)` logs every allowlisted mart. Log the tables the query actually uses instead, from `sql_guardrails._extract_referenced_identifiers` (line 159).
- **Usage telemetry, privacy-safe.** Add these fields to the query log: `prebuilt_id`, `engine`, `marts_used`, `row_count`, `status` and `elapsed_ms`. Keep the question and SQL hashed.
  - Add an optional `prebuilt_index` to `RunQueryRequest` (`api/models.py:33-36`, mirrored in `frontend/src/types/api.ts:77-81`) and a matching argument to `log_query` (`src/whyline/logs.py:30`).
  - In `dashboardStore.ts`, set it when a ready-made question runs and clear it when the user edits the question or SQL.
  - Add Vercel `track()` events: `question_run` with prebuilt_id and mart, `download` with mart, `map_view`.
  - The production log sits on the container's disk and is lost on restart, so also emit a structured line to Cloud Logging (`jsonPayload.event="query"`).
  - Add a weekly read-only report query to OPERATIONS.
- **Tests:** a unit test of the logged `marts_used`; frontend build and lint.
- **Acceptance:** the snow question returns snow days; a test query logs only its own mart.

## WP1: arrival-prediction accuracy (item 4, urgent)

**User question:** "Can I trust the countdown in my app?"

**Definitions:**
- For each visit with a measured arrival `A` (methods `shape_crossing` and `shape_crossing_gap`), and each horizon `h` in {1, 3, 5, 10, 15, 20, 30} minutes, take the prediction in effect at `A − h`. That's the latest stop-level (`is_trip_level = false`) `stg_rt_prediction_changes` row for that trip, start date and stop sequence with `feed_ts_utc ≤ A − h`. If that row is `new` or `changed`, its `predicted_ts_utc` is the prediction. If it is `dropped`, or no row exists yet, no prediction was on screen, and the case is counted as `no_prediction` instead.
- The error is `e = predicted_arrival − A`; a negative value means the bus came later than predicted.
- **Accurate** means within a band that tightens near arrival: −60 s to +60 s at 0–3 minutes out; −60 to +90 at 3–6; −90 to +150 at 6–12; −120 to +210 at 12–30. These are WMATA-style fixed bands; the glossary records them so they can be adjusted.
- **Padding** is the 5th-percentile lateness, `−P05(e)` when negative: the extra time a rider has to add (after Caltrans).

**Files:**
- `dbt/models/core/fct_prediction_accuracy.sql`: incremental by `service_date`, `insert_overwrite`, `full_refresh=false`, clustered on `route_id`. Grain: service date × trip × stop sequence × horizon.
  - Columns: `predicted_arrival_ts`, `prediction_made_ts`, `actual_arrival_ts`, `error_sec`, `within_band`, `arrival_method`, plus the route, stop and direction keys.
  - The as-of join: `stg_rt_prediction_changes` (partitions for the service date and the next day), with `qualify row_number() over (partition by visit, horizon order by feed_ts_utc desc) = 1` after `feed_ts_utc <= A − h`.
  - It rebuilds the last 3 service dates.
- `dbt/models/marts/realtime/mart_prediction_accuracy_by_route_day.sql`: route × date × horizon bucket, with `n_predictions`, `pct_within_band`, `median_error_sec`, `p05_error_sec`, `padding_sec`, `pct_late_over_2min`.
- Serving lists, schema, glossary and a ready-made question: "Which routes have the least reliable arrival predictions?"

**Tests:**
- A DuckDB test with three prediction changes for one visit, checking the right one is picked at each horizon, the band edges, and padding.
- dbt tests: unique grain; `horizon_min` in the allowed set; `error_sec` not null.

**Cost:** each night reads about 6M prediction-change rows for one or two days (about 0.6 GB, estimated) and the visits for those days: roughly 18 GB a month, about $0.11 at list price. Bound it with partition filters on `feed_ts_utc`.

**Owner:** none.

**Acceptance:** the fact covers every service date since 2026-10-29. The dual-run checks give a sanity range: median error falls as the horizon shrinks, and the accurate share at 0–3 minutes is above that at 12–30.

## WP2: crowding (item 3, urgent)

**User question:** "Will I get a seat? Which trips and stops are packed?"

**Definitions:**
- Occupancy levels are ordered: many seats (1), few seats (2), standing room only (3), crushed (4), full (5). "No data" and an empty value count as no data.
- For each report on a trip, the segment is the stop the vehicle is heading to: the report's `stop_id`, matched to the first stop sequence at or after the trip's progress, using `dist_along_m` from the poller.
- `segment_max_level` is the highest level reported on that segment.
- `trip_peak_level` is the highest level on the trip; `peak_stop` is where it first occurred.

**Files:**
- `dbt/models/core/fct_trip_occupancy.sql`: incremental by `service_date`, `full_refresh=false`. Grain: trip × stop sequence.
  - Columns: `n_reports`, `n_reports_with_data`, `max_level`, `max_level_label`, `first_report_ts`.
  - Source: `stg_rt_vehicle_positions` with `valid_for_timing`, non-repeat reports, joined to the schedule for the stop sequence.
- `dbt/models/marts/realtime/mart_crowding_by_route_hour.sql`: route × direction × service date × hour of departure from the first stop.
  - Columns: `n_trips`, `n_trips_with_data`, `pct_trips_with_data`, `pct_trips_few_seats_or_worse`, `pct_trips_standing_or_worse`, `peak_stop_mode`.
- `dbt/models/marts/realtime/mart_crowding_by_stop.sql`: stop × route × weekday or weekend × hour; the share of trips arriving standing or worse. This is the load-point view.
- Frontend: change the landing FAQ, which currently says there is no crowding, and the sources list. A glossary caveat explains that only some vehicles report occupancy and that RTD sets the thresholds.

**Tests:**
- A DuckDB test of segment assignment, `max_level` and the coverage share.
- dbt accepted values for `max_level` (1–5) and a coverage check, warn-level.

**Cost:** about 1.2M vehicle reports a day, one day per night: about 0.1 GB.

**Acceptance:** `pct_trips_with_data` is published next to every crowding share, and the 2026-10-29 totals reconcile with the raw counts above.

## WP3: missed trips, "ghost buses" (item 1)

**User question:** "My bus never came: how often does that happen on my route?"

**Definitions:** for each service date, the trips in the schedule (`fct_scheduled_stop_time`, distinct trips) are left-joined to `fct_trip_status`. Each gets an outcome:
- `delivered`: completed or partial with at least one visit;
- `canceled`: RTD marked it canceled;
- `vanished_no_vehicle`: it vanished and `had_vehicle` is false;
- `vanished_after_running`;
- `not_tracked`: never seen in either feed.

`pct_delivered = delivered / scheduled`. `pct_missed_likely = (canceled + vanished_no_vehicle + not_tracked) / scheduled`, with a caveat: feed gaps also produce untracked trips, so missed trips are only reported for hours where the stream was healthy, meaning it sealed every window with no stale alert.

**Files:**
- `dbt/models/marts/realtime/mart_service_delivered_by_route_day.sql`: route × direction × service date × hour band (early, AM peak, midday, PM peak, evening, night).
  - Columns: `n_scheduled`, `n_delivered`, `n_canceled`, `n_vanished_no_vehicle`, `n_vanished_after_running`, `n_not_tracked`, `pct_delivered`, `stream_healthy`.
  - `stream_healthy` comes from a small `fct_stream_health` table: window × count of sealed batches, built from `raw_gtfsrt_vp_stream` partitions.
- A ready-made question: "Which routes missed the most scheduled trips last week?"

**Tests:** a DuckDB test covering each outcome, including a scheduled trip with no status row becoming `not_tracked`.

**Cross-check:** compare with the service-availability figure in RTD's monthly bus reports (WP10).

**Cost:** small, about 60 MiB a night.

## WP4: wait time, bunching and gaps (item 2)

**User question:** "How long will I actually wait at my stop?"

**Definitions** (passengers are assumed to turn up at random):
- **Frequent service** is a scheduled headway of 15 minutes or less in that period. For these:
  - expected wait = `E[H²] / (2·E[H])` over the observed headways `H` between consecutive arrivals of the same route and direction at the stop;
  - scheduled wait uses the same formula over scheduled headways `S`;
  - **excess wait time (EWT) = expected wait − scheduled wait**.
- **Bunched:** `H < 0.25·S`. **Gap:** `H > 1.5·S`.
- **Infrequent service** keeps the RTD on-time share and adds "minutes late at the 90th percentile".

**Files:**
- `dbt/models/marts/realtime/mart_wait_by_stop_period.sql`: stop × route × direction × day type × period, built from `fct_stop_visit` with `scheduled_headway_sec`.
  - Columns: `service_class` (frequent or infrequent), `n_headways`, `expected_wait_sec`, `scheduled_wait_sec`, `excess_wait_sec`, `pct_bunched`, `pct_gap`, `pct_on_time`.
- `mart_wait_by_route_day`: the same rolled up to route and day.
- This reuses the cutover's headway logic, the `lag` over the same partition, but as a new model, so it doesn't conflict with #71.

**Tests:** a DuckDB test with a hand-computed EWT for a known sequence of headways, plus the bunched and gap thresholds.

**Cost:** about 0.33M visits a day: about 50 MiB a night.

## WP5: travel time, speed and slow zones (item 5)

**User questions:** "How long does the trip really take? Where does the bus crawl? Did the bus lane help?"

**Definitions:**
- A segment runs from stop sequence `n` to `n+1` on the same trip, using only visits with `shape_crossing` at both ends.
- Run time is `arrival(n+1) − departure_latest(n)`; when the departure is missing, use the arrival at `n`.
- Distance is `stop_dist_m(n+1) − stop_dist_m(n)`, using the stop's distance along the shape that every visit in `fct_stop_visit` already carries; speed is distance over time.
  - The poller computes `stop_dist_m` even for 2025 feeds without `shape_dist_traveled`, so no join to `stg_gtfs_stop_times` is needed and backfill dates work too.
  - Scheduled travel time comes from the arrival times in `fct_scheduled_stop_time`, which `fct_stop_visit` already joins.
- Trip run time is the departure from the first stop to the arrival at the last stop, compared with the schedule.
- **Buffer time index** = (p90 − p50) / p50 of trip run time.

**Files:**
- `dbt/models/core/fct_segment_traversal.sql`: incremental by service date. Grain: trip × segment.
  - Columns: `travel_sec`, `scheduled_travel_sec`, `distance_m`, `speed_kmh`, `hour`, and the midpoint latitude and longitude for maps.
- `dbt/models/marts/realtime/mart_segment_speed_by_hour.sql`: segment (stop pair) × route × day type × hour.
  - Columns: `p50_speed_kmh`, `p10_speed_kmh`, `p50_travel_sec`, `p90_travel_sec`, `scheduled_travel_sec`, `delay_ratio`.
  - It gets an `on_transit_lane` flag from WP7's Denver transit-lane layer.
- `mart_trip_runtime_by_route_day`: `p50_runtime_min`, `p90_runtime_min`, `scheduled_runtime_min`, `buffer_time_index`.
- **Bus-lane before and after:** for segments on lanes with a `YEAR_BUILT` inside the data range, compare speeds before and after. Data before the stream starts only becomes reliable once the backfill is calibrated, so this report is held until then.
- **Frontend:** `detectMapData` takes the segment midpoint latitude and longitude, so speeds show as points first. A follow-up adds line geometry if a deck.gl `LineLayer` is worth it.
- A ready-made question: "Where are the slowest bus segments at rush hour?"

**Tests:** a DuckDB test of segment pairing, the speed formula and the buffer time index.

**Cost:** about 70 MiB a night.

## WP6: scheduled frequency and span (item 6, static GTFS only)

**User question:** "How often does my bus run, and is my neighbourhood underserved?"

**Definitions:**
- Trips per hour by stop, route, direction and service date.
- Span: the first and last departure.
- **Frequent route:** average headway of 15 minutes or less from 6:00 to 21:00 on every day type (weekday, Saturday, Sunday), after TransitCenter's definition.
- **Service intensity per tract:** scheduled trips per hour at stops within 800 m (using `bridge_stop_tract` population weights), divided by thousands of residents.

**Files:**
- `dbt/models/marts/service/mart_service_frequency_by_stop.sql`: stop × route × day type × hour.
- `mart_frequent_network_by_route.sql`: route × day type, with span, headway by period and an `is_frequent` flag.
- `mart_service_intensity_by_tract.sql`.

All rebuild nightly from the current schedule; the service date is the next representative weekday, Saturday and Sunday.

**Tests:** a DuckDB test on a small schedule fixture, covering headways and the frequent flag.

**Cost:** under 50 MiB a night, because the schedule fact is partitioned.

**Note:** this doesn't depend on the cutover, so it can ship first along with WP0.

## WP7: safety and access, using existing fields plus Denver street layers (items 8 and 14)

**User question:** "Is it safe and accessible to get to this stop?"

**Existing fields:**
- add `ped_crashes_250m`, `bike_crashes_250m` and `ped_severe_250m` to `mart_crash_proximity_by_stop`;
- add `wheelchair_boarding` (from `dim_stop`) to `mart_access_score_by_stop`;
- add the share of sidewalk within 200 m by class and status (`dim_sidewalk_segment`);
- add `pct_stops_wheelchair_boarding` by route and by tract.

**New source `denver_streets_reference`:** one ingestor in the ArcGIS pattern, weekly via the 7-day skip. It pulls these layers with `outSR=4326`, and writes each as GeoJSON-in-CSV, the same way tracts are stored:
- HIN (326)
- transit lanes (349)
- transit signals (350)
- curb ramps (228)
- traffic signals (147)
- bike facilities (450)
- street centerlines (145; FUNCLASS)
- the pedestrian demand index (442)

Its JobSpecs are `raw_denver_hin`, `raw_denver_transit_lanes`, `raw_denver_transit_signals`, `raw_denver_curb_ramps`, `raw_denver_traffic_signals`, `raw_denver_bike_facilities`, `raw_denver_streets` and `raw_denver_ped_demand`, each partitioned by `_extract_date`.

**Core:** one dimension per layer (`dim_hin_segment`, `dim_transit_lane`, and so on), plus `bridge_stop_street_safety`, which for each stop records:
- whether it's on the HIN (within 30 m) and its HIN tier;
- the distance to the nearest signalised crossing;
- curb ramps within 50 m;
- bike facilities within 100 m;
- whether it's on a transit lane;
- whether it has a transit signal or TSP.

**Mart:** the safety and access columns join `mart_access_score_by_stop` and `mart_crash_proximity_by_stop`, and feed a new `mart_stop_walk_safety` with `walk_safety_flags` (for example "on the HIN, and no signal within 100 m").

**Tests:** the ingestor with paging mocked; DuckDB spatial tests use `ST_Distance` replaced by planar maths, as the existing tests do.

**Owner:** none. It uses the same public ArcGIS org.

**Cost:** about 15 MB of storage a week, kept for 30 days by a staging dedupe.

## WP8: RTD service alerts (item 10)

**User question:** "Is my stop closed or detoured? Why was service bad that day?"

**Ingestion:** don't put this in the stream poller. Adding a fifth output there would crash-loop the live poller on restore: `Window.seal` raises a KeyError on the restored rows dict. Instead:
- add `src/whyline/ingest/gtfs_alerts.py`, which fetches `Alerts.pb` and writes one row per alert × informed entity × active period (sample feed: about 273 entities);
- run it from the **`realtime-load` job** every 15 minutes: `infra/cloud-run/entrypoint.sh`'s `load)` case calls `python -m whyline.ingest.gtfs_alerts --gcs …` before the load, non-fatally. That needs no new scheduler, and it keeps running after `realtime-ingest` is paused at the cutover.

**Columns:** `feed_ts_utc, alert_id, cause, effect, header_text, description_text, url, active_start_utc, active_end_utc, agency_id, route_id, route_type, stop_id, trip_id`.

**JobSpec:** `raw_gtfsrt_alerts`, partitioned by DAY on `feed_ts_utc` with 90-day expiry. Pattern: `rtd_gtfsrt_alerts/snapshot_at=*/alerts.csv.gz`. It uses its own prefix, so the stream's stale check ignores it.

**Core:**
- `fct_alert`: one row per alert, with first and last seen, cause, effect and text, incremental.
- `fct_alert_entity_period`: alert × route or stop × active interval. Intervals with no end are closed at `last_seen + 15 min`.
- Both are kept permanently, so alert history survives the 90-day raw expiry.

**Marts:**
- `mart_alerts_by_route_day`: disruption hours by effect, stops closed, active detours.
- `mart_stop_closures`: currently and historically closed stops, with dates.

Both also join into the reliability views to explain skipped stops (`n_skipped` on visits at stops under a no-service alert).

**Frontend:** the FAQ line saying there are no service alerts changes; the attribution page gets the same RTD licence.

**Tests:**
- the protobuf parser on a fixture `.pb` built with `gtfs_realtime_pb2`;
- a JobSpec contract test against the header;
- DuckDB tests of interval sessionising.

**Owner:** after merge, rebuild the image and point `realtime-load` at it (two commands I'll give you).

**Cost:** about 26k rows a day, negligible.

## WP9: equity layers, EnviroScreen and DOTI equity (item 15)

**User question:** "Is service worse in the communities the state and the city prioritise?"

**Ingestor `equity_reference`:** yearly, checked weekly with the 7-day skip. It pulls:
- the EnviroScreen 2.0 tract layer, with fields renamed from their ArcGIS aliases (for example `ES_S_` becomes `enviroscreen_pctl`, plus the component percentiles);
- the EnviroScreen block-group layer with geometry, including its disproportionately-impacted flag;
- Denver's DOTI Equity Index (block groups, 572).

**JobSpecs:** `raw_enviroscreen_tract`, `raw_enviroscreen_block_group`, `raw_denver_doti_equity`.

**Core:** `dim_block_group` (geometry, impacted flag, DOTI scores) and `bridge_stop_block_group` (the block group containing the stop, via `ST_CONTAINS`). `fct_tract_enviroscreen`.

**Marts:**
- add `enviroscreen_pctl`, `is_disproportionately_impacted` and the DOTI equity score to `mart_vulnerability_by_stop`;
- a new `mart_service_equity_by_group`: on-time share, missed trips, crowding, EWT and service intensity for stops in impacted communities against the rest.

That mart is built after WP3, WP4 and WP6; until then it covers only the existing metrics.

**Licence note:** CDPHE data is public; credit it on the attribution page.

## WP10: RTD's reported on-time performance (item 13)

**User question:** "Why do WhyLine's numbers differ from RTD's?"

**Discovery:** find the RTD page that links the monthly Bus and Rail Operations PDFs; the board briefing documents and the reports pages are candidates. If none can be scraped, keep a tracked list of PDF URLs in `src/whyline/ingest/reference/rtd_operations_reports.txt`, and add the new month's URL each month (a monthly reminder in OPERATIONS).

**Ingestor `rtd_reported_performance`:**
- `pdfplumber` (a new dependency, pinned) extracts the bus service availability and on-time figures by service type, and the light-rail and commuter-rail on-time figures by line.
- It validates that each figure is a percentage between 0 and 100, and stops loudly if a layout changes.
- Rows: `report_month, mode, service_type_or_line, metric, value_pct, source_url`.

**JobSpec:** `raw_rtd_reported_performance` (monthly).

**Mart:** `mart_reported_vs_measured_by_month`: RTD's figure against WhyLine's for the same mode and month, after the cutover, using the RTD window. It notes that definitions differ: RTD measures at timepoints, WhyLine at every stop.

**Tests:** parse a saved PDF fixture (checked in, about 200 KB) and assert the expected numbers.

**Owner:** none, beyond the monthly URL if no index page exists.

## WP11: ridership (item 12)

**NTD:**
- Ingestor `ntd_monthly`, nightly, skipping when the newest `date` hasn't changed. It calls the Socrata API at `data.transportation.gov/resource/8bui-9xvu.json` with `ntd_id='80006'`, paging with `$limit` and `$offset`.
- JobSpec `raw_ntd_monthly`: `date, mode, tos, upt, vrh, vrm, voms`.
- Mart `mart_ridership_by_mode_month`: trips, trips per revenue hour, and year-on-year change. Data runs two months behind.

**RTD route boardings (owner action):** send a Colorado Open Records Act request to RTD for:
- monthly boardings by route;
- average weekday boardings by stop (APC), for the latest service period.

I'll draft the request text. When data arrives, ingest it as a reference file (`raw_rtd_boardings_route_month`) and weight the reliability, missed-trip and crowding metrics by riders: "riders affected per week".

**Tests:** the NTD ingestor with HTTP mocked; a DuckDB test of the year-on-year maths.

## WP12: jobs reachable by transit (item 11)

**User question:** "How many jobs can I reach in 45 minutes, at 8 am and at 8 pm?"

**Compute:** a weekly **GitHub Actions workflow** (`.github/workflows/weekly-access.yml`). Standard GitHub-hosted runners for public repos have about 16 GB of RAM, and a workflow file in the repo avoids any scheduler change. Steps:
1. Download the current GTFS zip, already archived in `gs://whylinedenver-rt-archive/static/…`.
2. Download a Colorado OpenStreetMap extract (Geofabrik `colorado-latest.osm.pbf`) and clip it to the RTD box with `osmium`.
3. Run `r5py` (Java 21) for a tract-centroid × tract-centroid travel-time matrix. It uses departure windows of Tuesday 7–9 am, 12–2 pm and 7–9 pm and Saturday 10 am–12 pm, sampled every 5 minutes, taking the median.
4. Join the LODES8 2023 workplace job counts (WAC S000 C000), aggregated from blocks to tracts.
5. Write `raw/job_access/extract_date=<d>/access.csv.gz` for the nightly load.

**JobSpec:** `raw_job_access`: `origin_geoid, window, minutes_threshold, jobs_reachable, total_jobs_region, extract_gtfs_md5`.

**Mart:** `mart_job_access_by_tract`: jobs within 30, 45 and 60 minutes, by window, with the regional share. It joins EnviroScreen and DOTI (WP9) for the equity view, and feeds `mart_access_score_by_stop` with the stop's tract value.

**Tests:** unit-test the LODES aggregation and the CSV contract; run the routing as a smoke test on a tiny fixture network in CI, kept optional, because a full run belongs in the workflow.

**Owner:** none. The workflow uses existing secrets, the same as the nightly workflows.

**Caveats for the glossary:** LODES suppresses or adjusts some small counts for privacy, and the travel times come from the schedule, not from what actually ran. A later variant could use measured travel times.

## WP13: hourly weather (item 16)

**Change:** extend `noaa_daily.py` with `--hourly`, or add a sibling `weather_hourly.py`.
- Pull Open-Meteo `archive-api` with `hourly=precipitation,snowfall,temperature_2m,wind_speed_10m` at the DIA station's coordinates, for the last 10 days. Fill the archive's 5-day lag from `/v1/forecast?past_days=7`.
- JobSpec `raw_weather_hourly` (`ts_utc, station, precip_mm, snowfall_cm, temp_c, wind_kmh, source`), partitioned on `ts_utc`.

**Core:** `fct_weather_hourly`.

**Marts:** a new `mart_weather_impacts_hourly`: reliability (from `fct_stop_visit`) by hourly precipitation band, snowfall over 0, and temperature band. This replaces daily-bin association with the actual weather in that hour. Later, `mart_reliability_by_route_day` keeps the daily bins, so nothing breaks.

**Tests:** extend `tests/ingest/test_noaa_daily.py` with an hourly fixture; a DuckDB join test.

## WP14: micromobility availability near stops, Veo (item 17)

**User question:** "Can I get to or from this stop without walking far?"

**Ingestion:** `src/whyline/ingest/gbfs_veo.py`, run from the **`realtime-load` job** like WP8, every 15 minutes, non-fatally.
- It fetches `free_bike_status` and `vehicle_types` from `…/name/den/gbfs`.
- It writes `raw/gbfs_veo/snapshot_at=<label>/vehicles.csv.gz`: `snapshot_ts_utc, vehicle_type_id, form_factor, propulsion, lat, lon, is_reserved, is_disabled, current_range_m`. It deliberately drops `bike_id`: GBFS rotates it for privacy, and keeping it adds nothing.
- Sanity checks: Veo's `system_information` timezone reports `America/Chicago`, wrong for Denver, so all times stay in UTC. Check that the vehicle count stays above 1,000, and that more than 95% of vehicles are inside the RTD box.

**JobSpec:** `raw_gbfs_veo_vehicles`, partitioned by DAY on `snapshot_ts_utc` with **30-day expiry**: about 8.4k rows × 96 a day.

**Core:** `fct_micromobility_near_stop`, incremental and permanent: stop × hour × form factor. Columns: `avg_available_within_200m`, `pct_snapshots_none_within_200m`. Only available vehicles count, meaning not reserved and not disabled.

**Mart:** `mart_micromobility_access_by_stop`: weekday and weekend by period. It also feeds the access score as an optional component.

**Tests:** the parser on a saved JSON fixture; the spatial aggregation on DuckDB.

**Licence:** check Veo's data terms before publishing, and credit Veo on the attribution page.

**Owner:** after merge, the same image update as WP8. WP8 and WP14 can share one release.

## WP15: "my stop" and "my route" scorecards (item 7)

**Marts:**
- `mart_stop_scorecard`: one row per stop, over the last 30 days.
- `mart_route_scorecard`: one row per route and direction.

Each pulls:
- on-time share and EWT (WP4);
- missed-trip share (WP3);
- crowding (WP2);
- prediction accuracy at 0–3 and 6–12 minutes (WP1);
- p90 trip time and buffer time index (WP5);
- frequency and span (WP6);
- pedestrian crashes, HIN, signals and curb ramps (WP7);
- active alerts (WP8);
- EnviroScreen, impacted flag and DOTI (WP9);
- job access (WP12);
- micromobility (WP14).

Each metric comes with its coverage, and missing components stay NULL; they're never zero.

**App:**
- new ready-made questions: "How is my stop doing?" (filtered by the stop-ID box) and "Report card for route 15";
- column descriptions written in plain language;
- the landing topic cards gain "Crowding", "Wait times" and "Disruptions".

**Tests:** DuckDB tests of the joins and of NULL handling.

## WP16: lower-priority sources (item 18), scoped as spikes

Each is a short investigation, which gets a work package only if it proves useful:
- **Event schedules** (Ball Arena, Coors Field and Empower Field calendars): flag event days and explain spikes in crowding and delay.
- **Traffic speeds:** CDOT data needs registration and commercial sources are paid. The question is whether traffic, rather than transit operations, explains slow segments.
- **Air quality and heat** (AirNow needs a free key): the comfort of waiting at stops.
- **Peer-agency feeds** (UTA, TriMet): benchmark on-time and EWT. Watch the storage cost.
- **Stop amenities** (shelters, benches): no open dataset. Ask RTD in the same records request as WP11.

---

## Releases (how the marts reach the app)

Because the API bakes in the dbt artifacts, new marts become visible in batches:

| Release | Contents | Steps |
|---|---|---|
| **R1**, after the November 5 review | WP0, WP1–WP6 marts switched to `allow_in_app: true` | I regenerate and commit the artifacts and build the API image with Cloud Build. You run one `gcloud run services update whylinedenver-api --image=<digest>`. Vercel deploys the frontend on merge. |
| **R2** | WP7, WP8, WP9 | Same, plus the `realtime-load` image update for WP8 (and WP14, if it's ready) |
| **R3** | WP10–WP14 | Same |
| **R4** | WP15 scorecards and the new topic cards | Same |

Between releases, merged marts build in BigQuery and are tested nightly, but the app doesn't list them until the next API deploy.

## Sequence and timing

| Order | Work package | Why now | Depends on |
|---|---|---|---|
| 1 | WP0 fixes (except the weather mart change) and WP6 frequency | Quick and independent of the cutover | none |
| 2 | WP1 prediction accuracy, WP2 crowding (facts first) | Raw expiry on 2027-01-27 | the stream (live) |
| 3 | WP3 missed trips, WP4 wait time, WP5 speeds (facts, unpublished) | Visit-based | `fct_stop_visit` and `fct_trip_status` (live) |
| 4 | November 5 review → #71 merges → WP1–WP5 marts published; WP0 weather mart | Validated visit method | #71 |
| 5 | WP8 alerts and WP14 Veo (one image release) | Explain disruptions; first and last mile | an owner image update |
| 6 | WP7 street layers, WP9 equity layers | Safety and equity context | none |
| 7 | WP10 reported on-time, WP11 NTD (and the records request) | Trust and ridership weighting | none |
| 8 | WP12 job access, WP13 hourly weather | Heavier compute | WP9 for the equity view |
| 9 | WP15 scorecards | Combines everything | WP1–WP14 |
| 10 | WP16 spikes | Optional | none |

**Nightly cost once everything lands:** about 0.9 GB of extra processing a night, about 27 GB a month or about $0.17 at list price. That's well inside the free 1 TiB plus the remaining budget. Extra storage is under $1 a month: the facts are permanent, and the raw snapshots expire after 30 or 90 days.

## Verification (applies to every work package)

- `make test`, `make lint` and `make test-ingest`. They're safe to run locally, because the suite refuses cloud clients.
- A DuckDB-rendered SQL test for every new model on fixture data.
- `dbt parse` and `compile` against production metadata. Dry-run every new model and report its bytes.
- Run the new ingestor once locally into `data/raw` (`--local`) against the real endpoint, and check row counts against the figures above.
- CI green, then merge under the standing permission. After merge:
  - confirm the nightly run builds the new models, and that their tests pass;
  - check the new mart in the app with its ready-made question;
  - update OPERATIONS with dated readings.
- **Cross-checks:**
  - WP3 against RTD's service-availability figures (WP10);
  - WP1 and WP4 for internal consistency (error falls as the horizon shrinks; EWT is at least 0 on average);
  - WP2 coverage against the raw occupancy counts;
  - WP12 against published job-access studies for Denver, as a rough sanity check.

## Owner actions, all in one place

1. Image updates for `realtime-load` after WP8 and WP14 merge: two `gcloud run jobs update` commands, which I'll provide.
1a. One API redeploy per release (R1–R4): `gcloud run services update whylinedenver-api` with the digest I build. The permission check blocks me from running it.
2. The records request to RTD for route and stop boardings and stop amenities (WP11 and WP16). I'll draft the text.
3. If no index page exists, a monthly link to the new RTD operations PDF (WP10).
4. Approving the cutover on November 5, which unlocks publishing WP1–WP5.
