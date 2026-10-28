# Realtime stop visits: continuous RTD capture and `fct_stop_visit`

Phase 0 plan, approved by the owner on 2026-10-28 with the departures in section 0. Built on branch `feat/rt-stop-visits`, cut from `origin/main` at `c8a177b`. Phases 1–5 go out as one PR each, because merge order matters:

1. Phases 1–2 merge and deploy first.
2. Phase 3 merges only after the new raw tables exist.
3. Phase 4 can merge at any time.
4. Phase 5 merges at cutover.

- **Reviewed revision:** `42ee2bc` (includes #63 medallion/Kimball, #65 artifacts, #66 docs). `origin/main` then moved to `c8a177b` (#67, #68: NOAA weather fallback only, no realtime files). Nothing was uncommitted except the untracked `skill-observations/`.
- **Evidence window:** read-only RTD polls on 2026-10-28, 14:25–15:20 UTC (08:25–09:20 MDT, weekday AM peak), plus BigQuery dry runs and metadata. A 24-hour run comes after Phase 1 (departure 8).

## 0. Decisions and departures needing your approval

1. **Visit logic runs in the poller (Python); dbt conforms it** (numbers in §3.1). Consequences:
   - two more poller outputs, so four staging files per 15 minutes instead of two (about +$0.35/month loader overhead);
   - the backfill, the archive replay and the calibration all run the same Python engine;
   - Phase 4's "backfill model" becomes the export + engine run + the dbt conforming path, plus the calibration SQL.
2. **Silver evidence models are views, not incremental tables** (`stg_rt_vehicle_positions`, `stg_rt_prediction_changes`). Under decision 1 nothing reads them every 15 minutes. Incremental copies would double the raw storage that the 90-day expiry exists to cap (about +$3.7/month at logical prices). The views have no window functions, so a constant date filter prunes the raw partitions underneath.
3. **Timing-rule refinements.** The live feed contradicts four of the written rules:
   1. *Near-side stops.* The arrival threshold becomes `min(stop pole distance, first valid STOPPED_AT position)`. Pure pole crossing would time a bus stopped short of the pole at its departure. Bus STOPPED_AT reports sit 18 m before the pole at p10, light rail 21 m before at the median.
   2. *`last_prediction` bounds:* `earliest = min(time the final predicted value was first published, that value − 60 s)`, `latest =` the first refresh without the stop. This reproduces the prompt's worked example (3:41:00–3:42:30). The text's "last refresh that listed the stop" would usually exclude the true arrival: 97.8% of drops come after the crossing, a median 36 s after (p90 61 s). The 60 s guard covers RTD's final-prediction error (p10 −24 s, p90 +32 s).
   3. *Origin stops.* There's no crossing at distance 0, so the first stop's event is the departure.
   4. *STOPPED_AT tolerance* is mode-specific: bus 100 m, rail 150 m (platform length; D2).
   5. *Dwell* follows the worked example: min = last − first STOPPED_AT, max = departure_latest − first STOPPED_AT. This can understate dwell by up to one report interval; documented.
4. **Rail misses the 30-second target.** Within-30-s windows: light rail 24.5%, commuter rail 30%, bus 84.9% (20-minute sample). The cause is the feed: rail vehicles report less often and irregularly (LR gap p90 76 s; CR median 40 s, p75 60 s), and a crossing is more likely to fall in a long gap. Projection quality is fine (LR lateral p90 11 m). No poller setting fixes this, so rail windows stay wider and are reported separately. The dashboard note's "usually within 30 s" holds for buses only; I propose "usually within 30 s for buses".
5. **IPv4 is probably free.** The billing catalog's "External IP Charge on a Standard VM" SKU gives the first 744 hours each month free. The locked decision stays IPv6-only, but the IPv4 fallback likely costs $0; confirm on the first bill.
6. **Physical storage billing (your option, not required).** `raw_gtfsrt_trip_updates` is 41.70 GiB logical but 1.14 GiB physical (37×); vehicle positions compress 17×. Switching `raw_denver` to physical billing would cut new raw-stream storage from about $3.7 to $0.7 a month at the 90-day cap, and cut existing raw storage too. It's a dataset-level setting with a 14-day cooldown.
7. **The VM service account also needs `roles/logging.logWriter`.** Without it the poller's logs never reach Cloud Logging, so the dead-poller alert can't fire. No BigQuery access.
8. **D1 (24 h) and D11 (memory) are measured with the Phase 1 poller in local mode**; the poller is the sampler. Phase 0 used a 20-minute peak sample plus an 8-minute follow-up. Volumes and costs below are busy-period upper bounds until then.
9. **The raw visit and trip-status tables partition by load hour** (`_ingested_at`, HOUR, 90-day expiry). Fifteen-minute reads then prune exactly, and backfill rows with 2025 service dates don't expire the moment they load. This needs `Partitioning` granularity and expiration support in the registry. The trip-update and vehicle tables stay DAY on `feed_ts_utc`.
10. **The backfill reads BigQuery raw through `EXPORT DATA`.** The raw bucket's lifecycle rule deletes every object after 180 days, so GCS snapshots before about 2026-05-01 are gone.
11. **Only final visits leave the poller.** Non-final state lives on the VM disk, and `is_final` is always true in loaded rows. Re-merging non-final visits every run would bill whole fact partitions (`t'`, §3.1).

## 1. Repository and live-state findings (reported, nothing changed or deleted)

| # | Finding | Evidence |
|---|---|---|
| F1 | The prompt's branch warning is stale: local `main` equals `origin/main` at `42ee2bc`. #66 already rewrote `dbt/models/README.md` to the medallion layout, so that drift item is fixed. | `git status`, `git ls-remote` |
| F2 | `engine_default=duckdb` in OPERATIONS is still true of the API (`api/models.py` default, `make api-deploy` sets `ENGINE=duckdb`). Since `41cef3b` the frontend requests BigQuery only, so the readback no longer describes what the dashboard queries. App queries now bill BigQuery. | `git show 41cef3b` |
| F3 | Orphans. `stg_denver`: `int_headway_adherence`, `int_headway_adherence_backup_20251109`, `int_scheduled_arrivals` (tables) and `int_rt_daily_coverage`, `int_rt_events_resolved`, `int_stop_headways_observed`, `int_stop_headways_scheduled`, `int_weather_by_date`, `stg_rt_events_daily_stats` (views). `raw_denver`: ten `__unpartitioned_bak` tables and `__tmp_gtfsrt_trip_updates_20260410183403_174a2a29` (left by a failed April load). The three `*_v2` datasets exist. No `__dbt_tmp` remains in `stg_denver`. `mart_denver.mart_reliability_by_stop_hour__dbt_tmp` is dbt's normal temp table with a 12-hour expiry. | `bq ls`, `bq show` |
| F4 | The Compute Engine API is disabled on the project. Enabling it creates an auto-mode `default` network, which can't do IPv6, so the runbook creates a custom VPC. | `gcloud compute networks list` |
| F5 | The `whylinedenver-raw` bucket deletes every object after 180 days and keeps soft-deleted objects 7 days; uniform bucket-level access is on (so IAM Conditions work). GTFS-RT strategy's "raw retention enables replay" holds for only 180 days in GCS; BigQuery raw is the only older copy. | `gcloud storage buckets describe` |
| F6 | Logical vs physical bytes: raw TU 41.70 / 1.14 GiB, raw VP 2.66 / 0.16 GiB, `stg_rt_events` 2.15 / 1.72 GiB (MERGE time travel). | `bq show` |
| F7 | `nightly-bq` runs `--select 'staging core marts'`, so new models join the nightly run automatically. If the dbt PR merges before the new raw tables exist, nightly fails. Ordering is enforced in the runbook. | `Makefile` |
| F8 | `bq_load` plans every JobSpec on each run, so new specs are picked up with no entrypoint change. If the `__ingestion_log` cache query fails, it returns an empty set and reloads the whole window; downstream must tolerate duplicate files. It maps CSV columns by position, so the poller's header must equal JobSpec order (contract test). | `bq_load.py:497-522` |
| F9 | `stg_rt_events` grain and ranking, and the VP parser dropping `stop_id`, `current_status`, `direction_id` and `start_date`, match the prompt. `fct_trip_observation` joins the schedule on the Denver event date, not GTFS `start_date`. | SQL, parser |
| F10 | The static ingestor also uses a legacy URL: `www.rtd-denver.com/files/gtfs/google_transit.zip` answers 308, then 307, then `nodejs-prod.rtd-denver.com` (Cloudflare, IPv6). It sends no `ETag` or `Last-Modified` (`no-store`), so changes are detected by hash. | `curl -I` |
| F11 | DML dry runs report every target column of every scanned partition, even for insert-only MERGE and anti-join INSERT. The official rule bills referenced columns (`q'`), plus `t'` (partitions actually updated) only when a row is updated or deleted. Deleting a whole partition bills 0 bytes. `insert_overwrite` through MERGE bills the replaced partitions. I treat dry-run DML figures as upper bounds. | dry runs; DML reference |

## 2. Discovery results

| # | Result | Design impact |
|---|---|---|
| D1 | Partial. Both feeds republish together every 30 s (40 gaps: p10 30, p90 31, max 31 s). `If-None-Match` returned 304 on 39 of 80 polls per feed, and no 200 ever repeated a header. TU 562 KB and VP 49 KB uncompressed; parse p50 78 ms / 34 ms on a laptop. Per refresh: 727 trips, 20,176 stop rows, 575 vehicles. Changed + new rows were 13.9% (p10 12.1%, p90 15.7%), with 250 stops dropped. Vehicle report gap p50 30 s, p90 30 s, p99 75 s, max 1,025 s; 4.2% repeats. The 24-hour run comes after Phase 1. | Matches the locked cadence; busy-rate volumes in §4 |
| D2 | Repeated against the current feed (`Sep26-37303-16-17-20261023-150015`). STOPPED_AT straight-line distance: bus p50 13 m, p90 83 m, p99 1.17 km; LR p50 35 m, p90 69 m; CR p50 40 m, p90 73 m. Along-route STOPPED_AT offset: bus p10 −18 / p50 +2 / p90 +74 m; LR −62 / −21 / +48 m; CR −51 / +12 / +64 m. Lateral offset of projected reports: bus p90 25 m, LR 11 m, CR 40 m. | Tolerance bus 100 m, rail 150 m; lateral limit 100 m; near-side rule (decision 3.1) |
| D3 | Confirmed. `shape_dist_traveled` is metres: its ratio to geodesic shape length is 1.000 for all 485 shapes. It's populated in all 815,809 `stop_times` rows and 385,972 shape points, never decreases, and puts each stop within 18 m of its interpolated shape point at p99 (max 50 m). | No projection needed for current stops |
| D4 | The vehicle `stop_id` is the current or next stop of the current trip in 97.5% of reports: 12,020 same, 5,502 next, 643 skip-ahead, 21 regressions, 424 (1.8%) not on the trip. Along-route regressions over 30 m: 102 of about 17k. | Window from `stop_id` plus a progress floor; stops not on the trip are evidence only |
| D5 | Rail doesn't behave like bus. Within-30-s windows: LR 24.5%, CR 30.0%, bus 84.9%. Report gaps: LR p50 30 / p75 40 / p90 76 s; CR p50 40 / p75 60 / p90 61 s; bus p90 30 s. Validity and projection are fine: LR 98% and CR 93% valid, LR lateral p90 11 m. Rail realtime stop IDs are platforms (615 stops with a parent, 138 stations), all present in static. Bus: 5.6% of distinct reports are over 100 m lateral (layovers, detours, wrong window), to investigate in Phase 1. | Rail flagged; tolerance 150 m; rail reported separately |
| D6 | Measured against our crossings: 97.8% of drops come after the bus crossed the stop (lag p10 22, p50 36, p90 61, p99 144 s); 2.2% come before it, by a median 179 s. 29% of drops had no crossing although the vehicle was reporting (first-report and invalid-report cases), so they fall back to `last_prediction`. Vanished trips: 59% left only the terminal (completed), but the terminal crossing was seen for just 36% of them; 40% vanished with more than 3 stops left. The 21.5% "not yet past" in the first sample was an artifact of 30 s-stale vehicle state. | A drop never times a visit that has a crossing; phantom guard; terminal rule; `last_prediction` bounds per decision 3.2 |
| D7 | `start_date` and the TU `timestamp` were always present. Trip relationships: 30,002 SCHEDULED and 40 CANCELED trip-refreshes; no ADDED or DUPLICATED; about 319 SKIPPED stop updates per refresh; no `delay` fields (826,630 checked). | Handled generically; ADDED trips get key −1 |
| D8 | No vehicle report later than its feed header and no per-vehicle backwards jump in 23,533 reports. Age at refresh: p50 3 s, p90 5 s, p99 255 s, max 598 s. | Stale threshold 120 s (about 1–2% excluded) |
| D9 | Confirmed from the official reference. `ST_LINELOCATEPOINT(line, point)` returns the 0–1 fraction of the closest point, ties unspecified; `ST_LINESUBSTRING` and `ST_LINEINTERPOLATEPOINT` exist. A 0-byte literal query on an out-and-back line snapped a bus at 427 m to 1,283 m (the return pass); `ST_LINESUBSTRING(line, 0, 0.5)` returned 427.5 m. | Not used on the hot path; available for SQL QA |
| D10 | Every endpoint has an IPv6 address: RTD realtime (Azure Front Door), RTD static (Cloudflare), `storage`, `*-docker.pkg.dev`, `logging`, `monitoring`, `oauth2`, `dl.google.com`/`update.googleapis.com` (COS updates), `gcr.io`. The metadata server and NTP are link-local. Private Google Access covers the IPv4 path to Google APIs. `github.com` has no AAAA and isn't needed. | Container must run with `--network host` (Docker's bridge is IPv4-only); Compute API must be enabled |
| D11 | The analysis process peaked at 356 MB RSS holding all static data as Python tuples. Building compact `array` geometry peaked at 222 MB, mostly transient (the zip held in memory plus temporary row lists). The poller will parse `stop_times` as a stream, straight into arrays. Target under 250 MB peak; measured in Phase 1 alongside the OS and logging agent. | Streamed compact static; no pandas in the loop |
| D12 | **Owner action.** RTD's license grants "non-exclusive, limited and revocable rights to use, reproduce, and redistribute the Data". It sets no polling limit and says nothing about archiving or derived metrics. RTD trademarks may not be used with the data, and RTD may change or revoke the terms at any time. | Please read the agreement before deploy |
| D13 | RTD: on time = "less than one minute early or five minutes late", against scheduled arrival at a stop or station, same window for bus and rail. Current marts use `abs(delay) <= 300` and count unknown delays as on time. **Decision:** −60 s < delay ≤ +300 s on arrival (departure at origin stops), unknown delays excluded from the denominator. Vars `on_time_early_sec: 60`, `on_time_late_sec: 300`. | Mart definition change, documented |
| D14 | Alerts feed: 114 alerts (99 active). Effects: 45 NO_SERVICE (mostly stop closures for construction), 27 DETOUR, 31 NO_EFFECT; 263 informed entities name route + stop. Closures likely explain many SKIPPED stops, and detours produce off-route reports. Ingesting it is out of scope; worth a later daily snapshot. | Report only |

## 3. Design

### 3.1 Where the visit logic runs: poller

Per-run upper bounds from dry runs of the existing tables (`fct_scheduled_stop_time` is 56.0 MiB for two service dates, `dim_trip` 6.5 MiB, a 10 MB minimum per referenced table) and peak volumes:

| Step (per 15-minute run) | A: dbt derives visits | B: poller derives visits |
|---|---:|---:|
| Loader `INSERT…SELECT` (10 MB minimum; TU changes ≈ 23 MiB at peak) + ingestion-log cache | 43 | 63 (4 files) |
| Silver evidence increments (VP, TU changes) | 33 | 0 (views) |
| Projection: reports × shape lines × per-date stop geometry | 56 | 0 |
| Bracketing state, drop rows, pending-visit recompute | 39 | 0 |
| New visit rows + watermark | — | 20 |
| Schedule join (2 dates; keys come from the schedule fact) | 56 | 56 |
| `fct_stop_visit` MERGE target keys, 3 partitions | 30 | 30 |
| `fct_trip_status` | 30 | 30 |
| Route-day + stop-hour marts (2 days) | 122 | 122 |
| **Total** | **≈ 409** | **≈ 321** |

B is about 90 MiB a run cheaper (≈ 250 GiB/month, about $1.5/month once past the free tier), inside the ~300 MiB dbt budget (258 MiB excluding the loader), and the projection is pure Python with offline unit tests. In SQL the projection needs per-vehicle state: the window depends on the previous report's own projection, which a set-based pass can't express. B's costs, handled below: one engine shared by stream, replay and backfill (§3.8); about 20 MB of static arrays on the VM; a bigger poller. A poller bug is recoverable by replaying the archive.

### 3.2 Poller (`JOB_TYPE=stream`)

New modules under `src/whyline/ingest/`, following the ingestor conventions (`io.get_logger`, `io.http_get_with_retry`, `build_parser`/`run`/`main`, manifests with `files.{name}.{path,row_count,bytes,hash_md5}`):

- `gtfs_rt_stream.py`: CLI, loop, batching, archive bundle, outbox and retry, checkpoints, heartbeat, and the replay and backfill entry points.
- `rt_engine.py`: pure logic. Feed parsing into rows (protobuf, no pandas), the TU diff, report cleaning, projection, crossings, dwell, finality and trip status.
- `rt_static.py`: static GTFS to compact `array` geometry per trip and shape, keyed by feed MD5. When `shape_dist_traveled` is missing (2025 feeds), it projects stops onto the shape monotonically.
- `gtfs_realtime.py`: change only the two default URLs to `open-data.rtd-denver.com/files/gtfs-rt/rtd/…`; the old job's output is otherwise unchanged.

Loop (the engine clock is the feed header time, never wall time, so replays are deterministic):

1. Every 15 s, GET both feeds with `If-None-Match`. A 304, or a header timestamp equal to the last processed, is skipped and counted.
2. Each new payload is appended gzipped to the current window's archive tar.
3. Parse, then diff TU against the last-emitted state keyed by `(trip_id, start_date, stop_sequence)`. Emit `new`/`changed` rows; `dropped` when a key leaves a trip that is still in the feed; `trip_new`/`trip_changed`/`trip_vanished` at trip level.
4. Clean VP. Mark repeats (same `(vehicle_id, report_ts)`), age (`feed_ts − report_ts`) and in-bbox. Emit every vehicle row with its projection fields.
5. Feed valid reports and TU events to the visit engine (§3.3), which emits final visits and closed-trip status rows.
6. At :00, :15, :30 and :45 UTC (wall clock), seal the window. Each of the four CSVs is gzipped (header always written, even with zero rows); write the manifest with per-window statistics, checkpoint, then upload in order. GCS writes use `if_generation_match=0`, so a 412 means already uploaded; that works with `objectCreator` alone.
7. Checkpoint every two minutes and on SIGTERM. The state pickle records the byte offsets of the open window files. On restart, files are truncated to those offsets, so nothing is emitted twice. State: about 20k TU keys, about 600 vehicles, about 1k active trips.
8. Outbox: sealed windows wait on disk until uploaded, with exponential backoff. ERROR is logged above 50 windows or 1 GB; the oldest archive tars are never dropped silently.
9. Static GTFS: fetched at start and every 6 hours from the canonical URL, swapped when the MD5 changes. The previous version is kept 36 hours for trips running past midnight. Each new zip is copied once to `gs://<archive>/static/rtd_gtfs/<md5>.zip`, and its MD5 is stamped on every row and manifest.
10. A heartbeat log line every 5 minutes reports refreshes, 304s and skips, row counts, outbox size and RSS.

### 3.3 Visit engine rules

State is held per trip instance `(trip_id, start_date)`; `service_date = start_date`.

- **Report validity:**
  - not a repeat;
  - age ≤ 120 s (drops about 1–2%: vehicles whose link lags more than RTD's own 2-minute accuracy claim);
  - inside the existing Denver bbox;
  - lateral offset ≤ 100 m (bus p90 25 m and CR p90 40 m; detours and layover yards exceed it);
  - projected distance within [first stop − 100 m, last stop + 100 m] (interlining rule).
- **Projection:** nearest point on the trip's shape, limited to the stretch between the previous stop and the reported `stop_id`. `stop_id` resolves to its first occurrence at or after the vehicle's progress index, which handles loops; ±150 m applies when STOPPED_AT. The search is also clamped to at least the last valid distance − 50 m.
- **`shape_crossing` / `shape_crossing_gap`:**
  - Arrival happens where along-route distance crosses the threshold, which is the pole distance, or the first valid STOPPED_AT position at that stop if smaller (the near-side rule).
  - Bounds come from the bracketing valid reports. Linear interpolation gives the point estimate, except where `after` is at rest at the threshold; there the midpoint is used.
  - Within 30 s or not decides between the two method labels.
  - Several stops crossed between two reports each get their own interpolation.
- **Dwell and departure:** only STOPPED_AT reports for that stop within tolerance (bus 100 m, rail 150 m) count. Departure lies between the last such report and the next report.
- **`last_prediction`:** used only without a crossing, and only when the trip has been shown to run: a valid vehicle report at some point, or at least two stops dropped in sequence while the trip stayed listed. The arrival is the final predicted arrival. Bounds: `earliest = min(when that value was first published, value − 60 s)`, `latest =` the first refresh without the stop, with the point clamped into them.
- **Terminal stop at vanish:** if the trip was running, only the final stop remained, and its final prediction is no later than the vanish time + 120 s, the visit is recorded with the same rule. Otherwise the remaining stops get no visits and the trip is counted `vanished`.
- **Skipped:** a stop update with `SKIPPED` gives `skipped = true` with a null arrival. **CANCELED** trips get no visits, only a status row. ADDED and DUPLICATED trips not in static are evidence only and appear in status.
- **Finality:**
  - A visit is final when its arrival is known, the stop has dropped or the trip has vanished, and the vehicle has left the stop (one later report past it) or 20 minutes of feed time have passed.
  - A trip closes 10 minutes after it is absent from both feeds; its pending visits are then finalized and one status row is emitted.
- **Flags:** `trip_switch_at_terminal` when the bracketing reports carry different `trip_id`s; `prediction_error_sec` where a crossing and a prediction both exist.

### 3.4 Outputs and GCS layout

- **Standard staging:** `gs://whylinedenver-raw/raw/rtd_gtfsrt_stream/snapshot_at=YYYY-MM-DDTHH:MM/{tu_changes,vp_reports,stop_visits,trip_status}.csv.gz` + `manifest.json`. Reusing `snapshot_at=` means the loader's prefix and date logic work unchanged. A new lifecycle rule deletes this prefix after 7 days, alongside the existing 180-day rule.
- **Coldline archive:** `gs://whylinedenver-rt-archive/rtd_gtfsrt/date=YYYY-MM-DD/HHMM.tar`, holding members `{tu,vp}/<header_ts>.pb.gz`, plus `static/rtd_gtfs/<md5>.zip`. About 96 objects a day; kept forever.

Raw tables (registry order is CSV order). All are NULLABLE plus the four loader meta columns, all have 90-day partition expiry, and all are clustered on `route_id, trip_id`.

| Table (partition) | Columns |
|---|---|
| `raw_gtfsrt_tu_changes` (DAY `feed_ts_utc`) | `feed_ts_utc, change_type, trip_id, start_date, route_id, direction_id, trip_schedule_relationship, tu_timestamp_utc, tu_vehicle_id, stop_sequence, stop_id, arrival_ts_utc, departure_ts_utc, arrival_delay_sec, departure_delay_sec, stop_schedule_relationship` (dropped rows carry the last emitted times) |
| `raw_gtfsrt_vp_stream` (DAY `feed_ts_utc`) | `feed_ts_utc, report_ts_utc, entity_id, vehicle_id, vehicle_label, trip_id, start_date, route_id, direction_id, trip_schedule_relationship, stop_id, current_status, lat, lon, bearing, speed_mps, occupancy_status, report_age_sec, is_repeat, in_bbox, dist_along_m, lateral_offset_m, valid_for_timing` |
| `raw_gtfsrt_stop_visits` (HOUR `_ingested_at`) | `service_date, trip_id, start_date, stop_sequence, stop_id, stop_role, route_id, direction_id, trip_headsign, vehicle_id, arrival_method, arrival_ts_utc, arrival_earliest_ts, arrival_latest_ts, departure_earliest_ts, departure_latest_ts, dwell_min_sec, dwell_max_sec, skipped, stopped_observed, before_report_ts, before_dist_along_m, after_report_ts, after_dist_along_m, stop_dist_m, nearest_offset_m, last_predicted_arrival_ts, last_prediction_published_ts, trip_switch_at_terminal, low_confidence, is_final, data_version, static_md5, emitted_at` |
| `raw_gtfsrt_trip_status` (HOUR `_ingested_at`) | `service_date, trip_id, start_date, route_id, direction_id, final_schedule_relationship, outcome, first_seen_ts, last_seen_ts, first_vp_ts, last_vp_ts, had_vehicle, n_stops_static, n_visits, n_shape_crossing, n_last_prediction, n_skipped, data_version, static_md5, closed_at` |

`outcome` ∈ {`completed`, `canceled`, `vanished`, `never_started`, `partial`}.

### 3.5 Loader (Phase 2)

- `registry.py`: four new `JobSpec`s; `Partitioning` gains `granularity="DAY"` and `expiration_days=None`, which `ensure_destination_table` maps onto `TimePartitioning(type_, field, expiration_ms)`.
- `bq_load.py`:
  - After discovery, log `STREAM_STALE newest=<label> age_min=<n>` at WARNING when the newest `rtd_gtfsrt_stream` batch is older than 30 minutes.
  - Log `STREAM_MISSING` when the window holds none and the time is past the first expected batch.
- The new raw tables are created by the first load after the image deploy. The dbt PR merges only after they exist (F7).

### 3.6 dbt (Phase 3)

- **Sources:** the four tables, each with `freshness` + `filter` on a bounded window. `loaded_at_field` is `_ingested_at` for visits and status, `feed_ts_utc` for TU and VP. Warn after 30 minutes, error after 60.
- **Silver:**
  - views `stg_rt_vehicle_positions` (typed; excludes repeats, stale reports and reports outside the bbox), `stg_rt_prediction_changes`, `stg_rt_stop_visits` and `stg_rt_trip_status`;
  - `stg_gtfs_stop_times` gains `shape_dist_traveled`;
  - new view `stg_gtfs_shapes`: one `GEOGRAPHY` line per `_extract_date × shape_id`, with `is_valid` and `length_m`, for QA and maps.
  - The per-service-date nightly stop-geometry table is not built: under decision 1 no 15-minute model reads static geometry.
- **Core `fct_stop_visit`:**
  - Incremental merge on `[service_date, trip_id, stop_sequence]`, partitioned by `service_date`, clustered on `route_id, stop_id`. Incremental predicates limit it to the last 3 dates; a var widens that for the one-off backfill load.
  - Source: rows with `_ingested_at > <watermark>`. The watermark is inlined as a constant by a macro, like `latest_extract_date`. Rows are deduplicated within the batch. Backfill rows dated on or after `stream_start_date` are dropped.
  - Keys and schedule come from joining `fct_scheduled_stop_time` on `(service_date, trip_id, stop_sequence)`. A visit with no scheduled row gets keys −1.
  - Derived columns: `stop_visit_key`, `arrival_ts_mst`, `arrival_hour_mst`, `arrival_window_sec`, `within_30s`, `scheduled_arrival_ts`, `scheduled_departure_ts`, `scheduled_headway_sec` (LAG over the schedule at stop × route × direction), `delay_sec` (null when unknown; departure-based at origin stops), `prediction_error_sec` and `_ingested_at`.
  - `full_refresh: false` protects history once raw expires.
- **Core `fct_trip_status`:** merge on `[service_date, trip_id]`, keys from `dim_trip`/`dim_route` valid on the service date.
- **Tests:**
  - grain uniqueness (bounded `where`);
  - accepted values for `arrival_method` and `outcome`;
  - new generic test `expression_is_true`: `earliest ≤ arrival ≤ latest`, and no non-null arrival without a method;
  - warn-level monotonic arrival by `stop_sequence`;
  - singular test: raw visits loaded 2–3 days ago all appear in the fact (finality before expiry, bounded);
  - DuckDB-rendered SQL tests for the conforming CTE (the existing `tests/sql` pattern).
- **Kimball check:**
  - Business process: a vehicle serves a stop.
  - Atomic transaction grain: as declared above.
  - Conformed dimensions: date, stop, route and trip, Type 2, versions valid on the service date.
  - Degenerate dimensions: `trip_id`, `stop_sequence`, `vehicle_id`, `arrival_method`, `data_version`.
  - Natural keys carried for the marts.
  - Measures (non-additive; averaged or quantiled): windows, dwell, delay, prediction error.
  - Disclosed deviations: `trip_headsign` is copied from `dim_trip` because the prompt asks for it; keys come through the schedule fact, which uses the same resolution logic and avoids three dimension scans per run.
  - Bus matrix: `fct_stop_visit` (date, stop, route, trip) and `fct_trip_status` (date, route, trip).
- **Selection:** `dbt-run-realtime` adds `stg_rt_stop_visits stg_rt_trip_status fct_stop_visit fct_trip_status` (views are free DDL).

### 3.7 Monitoring (free)

- dbt source freshness, nightly, with filters.
- `STREAM_STALE` and `STREAM_MISSING` warnings from `realtime-load`, with a log-match alert policy on them (email channel).
- A log-based counter on the poller heartbeat, with a metric-absence alert after 30 minutes.
- The billing catalog has no alerting SKU; log-based metrics fall within the 150 MiB free metric volume.

### 3.8 Replay, backfill, calibration

- **Replay:** `gtfs_rt_stream --replay gs://…archive… --from D1 --until D2 --out <dir>`. It reads the tars in order, loads the static zip by the MD5 in the manifests, and runs the same engine into the same CSV layout under `raw/rtd_gtfsrt_replay/…`, which isn't a registered path, so nothing loads it by accident. Built in Phase 1, before the first raw partition can expire. The Phase 6 drill replays a day and diffs it against the fact.
- **Backfill (2025-10-23 → stream start):**
  - `EXPORT DATA` writes the needed columns of the two old raw tables to Parquet. The dry run is 11.4 GiB + 0.8 GiB = 12.2 GiB, inside the free tier; the prompt estimated 44 GiB because it counted all columns.
  - The GTFS extracts used by each date come from `fct_scheduled_stop_time.gtfs_extract_date`, exported from `raw_gtfs_stop_times`, `raw_gtfs_trips` and `raw_gtfs_shapes` (about 50 MiB per version).
  - The engine runs in `--backfill` mode. Its windows are bounded by the snapshot TU next stop (no `stop_id` or status in the old rows), giving methods `backfill_shape_crossing` and `backfill_prediction`. The same phantom and cancellation rules apply. `low_confidence` is set when a gap exceeds 20 minutes.
  - Output loads through a one-off registered path as `data_version = 'backfill_v1'`. The owner runs it as a one-off Cloud Run execution.
- **Calibration (after 2–4 weeks of stream):** replay the archive thinned to the refresh nearest each :00/:15/:30/:45, with vehicle `stop_id` and status stripped, in backfill mode. A written SQL query then compares the result with `stream_v1` visits on the grain: median and p90 absolute error, bias, and coverage loss. Results go to `METRICS_GLOSSARY.md` before backfilled metrics are published.

### 3.9 Downstream (Phase 5, merged at cutover)

- **Marts read `fct_stop_visit`** at the same grains.
  - `n_events` = visits with an arrival; `n_reported_events` = visits with a known delay.
  - `pct_on_time`, mean and median delay and p90 use known delays only, under the D13 window.
  - Stop-hour headways come from consecutive visits per route × direction × stop, with adherence against `scheduled_headway_sec`.
  - Appended columns: `data_version`, `n_scheduled`, `n_canceled_trips`, `pct_observed`, `n_skipped`, `pct_shape_crossing`, `pct_last_prediction`, `pct_within_30s` and `median_window_sec`.
  - Partitions before cutover keep the legacy method (null `data_version`) until the calibrated backfill is published and rebuilt.
- **Old facts:** after cutover, `fct_trip_observation` and `fct_stop_arrival` are frozen and relabelled "legacy: sampled predicted terminal arrival" in the schema and docs; they're dropped from the realtime selection.
- **Docs to update:** `schema.yml` ×3, `exposures.yml`, `CONTRACTS.md`, `METRICS_GLOSSARY.md`, `GTFS_RT_Strategy.md`, `DATA_PIPELINE.md`, `OPERATIONS.md`, `dbt/models/README.md`, `infra/cloud-run/README.md`, `QA_Validation_Guide.md`, `docs/diagrams/data_model_overview.mmd`, `BQ_Naming_and_Time.md` and `ARCHITECTURE.md`.
- **App wiring:**
  - Mart names are unchanged, so `ALLOWLISTED_MARTS` stays as is.
  - `api/models.py` and `frontend/src/types/api.ts` don't list mart columns; to be verified.
  - New columns reach the schema brief only after artifacts are regenerated and the API is redeployed.
  - The dashboard note goes under the intro in `frontend/src/app/app/page.tsx`, with the cutover date from a constant.

## 4. Cost model

Prices are list prices from the Cloud Billing Catalog API on 2026-10-28, in USD:

| Service | Rate |
|---|---|
| BigQuery analysis | $6.25/TiB after 1 TiB free each month |
| BigQuery storage, logical | $0.02 active / $0.01 long-term per GiB-month (10 GiB free) |
| BigQuery storage, physical | $0.04 active / $0.02 long-term per GiB-month |
| BigQuery streaming insert | $0.05/GiB |
| Cloud Storage, Standard (us-central1) | $0.02/GiB-month (5 GiB free); Class A $0.005 per 1,000 (5,000 free) |
| Cloud Storage, Coldline | $0.004/GiB-month; Class A $0.02 per 1,000; retrieval $0.02/GiB; 90-day minimum storage |
| `pd-standard` | 30 GiB-month free |
| `pd-balanced` | $0.10/GiB-month (no free tier) |
| External IPv4 on a standard VM | 744 h free, then $0.005/h |
| e2-micro | free tier (us-central1) |
| Artifact Registry | 0.5 GiB free, then $0.10/GiB-month; same-region pulls free |
| Logging | 50 GiB free each month |

Daily averages are taken as 70% of the peak rate until D1.

| Component | Volume | Monthly |
|---|---|---:|
| VM, 30 GB `pd-standard`, IPv6 | free tier | $0 |
| Staging GCS (7-day rule) | ~2.3 MB/window, 14.4k writes | ~$0.10 |
| Coldline archive | ~13–18 GiB/month, 2.9k writes | $0.11 in month 1, $0.21 by month 3, then +$0.05–0.07 each month |
| Raw stream storage (logical) | TU changes ~6.1M rows/day × 260 B; VP 1.2M × 290 B; visits ~0.33M × 350 B | $1.2–1.7 in month 1, **$3.7–5.2** at the 90-day cap; physical billing ~$0.7 |
| `fct_stop_visit` + status | ~3.3 GiB/month, permanent | $0.07 → $0.50 at 12 months → $0.90 at 24 |
| Queries after cutover | (258 dbt + 63 loader) MiB × 2,880 runs + ~0.19 TiB nightly ≈ 1.07 TiB | ~$0.45 |
| Queries today (old realtime ~440 MiB/run) | ≈ 1.38 TiB | ~$2.4 |
| **Dual-run** (old + new) | ≈ 2.28 TiB/month rate | about $8/month rate, so roughly **+$2–2.5 for a 10-day dual run** |

New-component storage at 3 / 12 / 24 months (logical): about $4.1 / $5.2 / $6.4; with physical billing about $1.0 / $1.7 / $2.6, by then mostly Coldline.

**Budget arithmetic.**

1. Non-query costs at month 3 come to about $7.1: existing BigQuery storage ~$2.5 (falls once the backups are dropped), new raw ~$3.7, facts ~$0.2, GCS ~$0.4, Artifact Registry ~$0.3.
2. That leaves ~$2.9 for queries: 0.46 TiB billable + 1 TiB free = 1.46 TiB/month.
3. Subtract nightly (~0.19 TiB): 1.27 TiB / 2,880 runs = **≈ 460 MiB per 15-minute run** for the realtime job.
4. B needs ≈ 321 MiB, so it fits with ~140 MiB of headroom. The dual run (≈ 761 MiB) doesn't fit, which is why it's bounded to 7–14 days.

## 5. Phases and acceptance

| Phase | Files | Accept |
|---|---|---|
| 0 | this document → `docs/technical/plans/realtime-stop-visits.md`; observation-log entries | your approval |
| 1 poller | `ingest/gtfs_rt_stream.py`, `rt_engine.py`, `rt_static.py`, `gtfs_realtime.py` (URLs); `infra/stream-vm/cloud-init.yaml` (systemd unit + install); `entrypoint.sh` `stream)` (`exec`); Makefile `ingest-gtfs-rt-stream`, `replay-gtfs-rt`; `tests/ingest/test_rt_engine.py`, `test_gtfs_rt_stream.py` | Unit tests cover the prompt's worked examples exactly (3:41:56, 3:41:54, 3:42:10, dwell 30–60 s), a corner, a far-side stop, a stop short of the pole, a loop serving a stop twice, a gap over 30 s, phantom vanish, cancel, dedup and staleness, diff and restart, and checkpoint truncation. A live local run of ≥ 10 min reports skips, changed-row rate, drops and peak RSS. Then a 24-hour run for D1 and D11, with D5 and D6 split by mode. It runs locally in the background, or as the VM's first day, read from the per-window manifests. Volumes and costs are then recomputed from daily totals. |
| 2 load | `registry.py`, `bq_load.py`; contract test (poller CSV header = JobSpec order; a sample batch parses with the registry types); registry tests; `infra/stream-vm/alert-*.json` | `make test`, `make lint`; a dry run of each new table's `CREATE TABLE` DDL (partitioning, expiry, clustering) validates the options without creating anything |
| 3 dbt | `sources_raw.yml`; silver views; `stg_gtfs_stop_times`, `stg_gtfs_shapes`; `fct_stop_visit`, `fct_trip_status`; watermark macro; `expression_is_true` test; Makefile selection | `dbt parse` and `compile`. Dry-run MiB is reported for every part that reads existing tables (schedule, dimensions, marts). The new stream tables don't exist until the owner deploys Phases 1–2, so their reads are estimated from row sizes, then measured from `INFORMATION_SCHEMA.JOBS` in the first dual-run day. Total under the §4 budget. |
| 4 backfill | `EXPORT DATA` SQL; `--backfill` mode; calibration SQL | dry-run bytes reported; backfill mode unit-tested on a fixture; calibration query compiles |
| 5 downstream | marts, schema, exposures, docs, dashboard note, glossary | `make test`, `make lint`, `make frontend-build`; docs list every changed definition |
| 6 dual run | checklist (below) | owner executes |

Each PR description states what was verified, how, and what wasn't.

## 6. Dual-run and cutover checklist (owner)

Run both pipelines for at least 7 days, including a weekend.

1. **Completeness:** visits vs scheduled stop events (minus cancelled trips) per route, direction, day and hour. Explain every route-hour below 90%: feed gap, vehicle not reporting, phantom guard, attribution, or bug.
2. **Accuracy:**
   - `arrival_window_sec` distribution, `within_30s` share and method mix, by mode, route and hour;
   - `shape_crossing` vs `last_prediction` where both exist;
   - STOPPED_AT check: `arrival_latest_ts` is at or before the first STOPPED_AT report;
   - 20 or more visits spot-checked against archive replays;
   - optionally, a field check or RTD's published OTP.
3. **Old vs new by route-day**, using new marts built into a scratch dataset (`BQ_DATASET_MART=mart_denver_eval`, the #63 pattern). Every difference is classed as an intended change, a fixed defect, or a regression.
4. **Determinism:** replay one day from the archive and diff it against the fact.
5. **Cost:** seven days of `INFORMATION_SCHEMA.JOBS` billed bytes, old vs new.
6. **Cutover:** merge Phase 5 and deploy the digest; rebuild the mart partitions from the stream start; pause `realtime-ingest`; take the old models out of `dbt-run-realtime`; relabel them.
7. **Later:** after calibration, publish `backfill_v1` and rebuild the earlier partitions.

## 7. Runbook (owner commands, in order)

Project `whyline-denver`, region `us-central1`, zone `us-central1-a`. Each step lists its rollback.

```bash
# 0. Record rollback state
gcloud run jobs describe realtime-load  --region=us-central1 --format='value(template.template.containers[0].image)'
gcloud run jobs describe realtime-ingest --region=us-central1 --format='value(template.template.containers[0].image)'

# 1. APIs (rollback: none needed; leave enabled)
gcloud services enable compute.googleapis.com --project=whyline-denver

# 2. Archive bucket (rollback only while empty: gcloud storage buckets delete gs://whylinedenver-rt-archive)
gcloud storage buckets create gs://whylinedenver-rt-archive --project=whyline-denver \
  --location=us-central1 --default-storage-class=COLDLINE \
  --uniform-bucket-level-access --public-access-prevention

# 3. Staging lifecycle: keep the existing 180-day rule and add a 7-day rule for the stream prefix
#    (rollback: re-apply the 180-day-only JSON)
cat > /tmp/raw-lifecycle.json <<'JSON'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":180}},
         {"action":{"type":"Delete"},"condition":{"age":7,"matchesPrefix":["raw/rtd_gtfsrt_stream/"]}}]}
JSON
gcloud storage buckets update gs://whylinedenver-raw --lifecycle-file=/tmp/raw-lifecycle.json

# 4. Service account + least privilege (rollback: remove the bindings, then delete the account)
gcloud iam service-accounts create rt-stream-poller --project=whyline-denver --display-name="RTD stream poller"
SA=rt-stream-poller@whyline-denver.iam.gserviceaccount.com
gcloud storage buckets add-iam-policy-binding gs://whylinedenver-rt-archive --member=serviceAccount:$SA --role=roles/storage.objectCreator
gcloud storage buckets add-iam-policy-binding gs://whylinedenver-raw --member=serviceAccount:$SA --role=roles/storage.objectCreator \
  --condition='title=stream-prefix,expression=resource.name.startsWith("projects/_/buckets/whylinedenver-raw/objects/raw/rtd_gtfsrt_stream/")'
gcloud artifacts repositories add-iam-policy-binding realtime-jobs --location=us-central1 --member=serviceAccount:$SA --role=roles/artifactregistry.reader
gcloud projects add-iam-policy-binding whyline-denver --member=serviceAccount:$SA --role=roles/logging.logWriter --condition=None

# 5. Network: custom VPC, dual-stack subnet, external IPv6, Private Google Access, IAP SSH only
#    (rollback: delete the firewall rule, subnet, network)
gcloud compute networks create whyline-rt --project=whyline-denver --subnet-mode=custom
gcloud compute networks subnets create whyline-rt-usc1 --network=whyline-rt --region=us-central1 \
  --range=10.20.0.0/24 --stack-type=IPV4_IPV6 --ipv6-access-type=EXTERNAL --enable-private-ip-google-access
gcloud compute firewall-rules create whyline-rt-iap-ssh --network=whyline-rt --direction=INGRESS \
  --allow=tcp:22 --source-ranges=35.235.240.0/20

# 6. Merge Phases 1–2, build, and deploy the reviewed digest to BOTH jobs (rollback: the step-0 digests)
gcloud builds submit --project=whyline-denver --region=us-central1 --config=infra/cloud-run/cloudbuild.yaml \
  --substitutions=_IMAGE_URI=us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime:<sha> .
IMAGE_URI=us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime@sha256:<digest>
gcloud run jobs update realtime-ingest --region=us-central1 --image="$IMAGE_URI"
gcloud run jobs update realtime-load   --region=us-central1 --image="$IMAGE_URI"

# 7. VM: e2-micro, COS, 30 GB pd-standard, no external IPv4 (rollback: stop or delete the instance; data stays in GCS)
gcloud compute instances create rt-stream-poller --project=whyline-denver --zone=us-central1-a \
  --machine-type=e2-micro --image-family=cos-stable --image-project=cos-cloud \
  --boot-disk-type=pd-standard --boot-disk-size=30GB \
  --network-interface=subnet=whyline-rt-usc1,stack-type=IPV4_IPV6,ipv6-network-tier=PREMIUM,no-address \
  --service-account=$SA --scopes=cloud-platform --shielded-secure-boot \
  --metadata-from-file=user-data=infra/stream-vm/cloud-init.yaml \
  --metadata=image-uri=$IMAGE_URI,gcs-bucket=whylinedenver-raw,archive-bucket=whylinedenver-rt-archive,google-logging-enabled=true

# 8. Verify: heartbeat in Logs Explorer; objects at :00/:15/:30/:45; the next realtime-load loads four files; the four raw tables exist
bq show raw_denver.raw_gtfsrt_stop_visits

# 9. Only now merge Phase 3 (nightly picks up the new models), rebuild, and redeploy per step 6

# 10. Alerts: email channel + log-match policy on STREAM_STALE / STREAM_MISSING + heartbeat absence
#     (JSON policy files in infra/stream-vm/; created with gcloud alpha monitoring policies create --policy-from-file=…)

# Upgrade or rollback the poller: change the digest in metadata and restart
gcloud compute instances add-metadata rt-stream-poller --zone=us-central1-a --metadata=image-uri=<previous-or-new digest URI>
gcloud compute ssh rt-stream-poller --zone=us-central1-a --tunnel-through-iap --command='sudo systemctl restart whyline-stream'

# IPv4 fallback (likely $0 under the 744-hour tier; rollback: delete-access-config)
gcloud compute instances add-access-config rt-stream-poller --zone=us-central1-a --access-config-name=external-nat

# Optional (decision 6): physical storage billing on raw_denver
bq update --storage_billing_model=PHYSICAL whyline-denver:raw_denver
```

## 8. Risks and open questions

- **Rail accuracy (D5).** If tuning can't close the gap, rail keeps wider windows; they're flagged, not dropped.
- **Premature drops (D6).** 2.2% of drops come a median 3 minutes before arrival; a `last_prediction` visit built on one of those is early. Re-measured over 24 hours and reported by method in the dual run.
- **Coverage gaps.** 29% of drops had no crossing even though the vehicle was reporting. Terminal crossings were seen for only 36% of completed trips, and 5.6% of bus reports were over 100 m lateral. Phase 1 investigates each before the dual run, aiming for more `shape_crossing` and less `last_prediction`.
- **e2-micro CPU bursts** during static reloads (about 4 s on a laptop) and gzip at seal; measured in Phase 1.
- **COS log collection, cloud-init re-runs and IPv6 address selection inside Docker** are verified at the first deploy; the fallback is in the runbook.
- **Free-tier dependence.** Another e2-micro or IPv4 VM on the billing account would consume the free hours.
- **Duplicate visits** after a lost VM disk or two pollers running at once. The checkpoints prevent normal-restart duplicates, and the grain test catches the rest.
- **DST.** The 2026-11-01 DST change falls inside the likely dual run. GTFS times count from noon − 12 h; the existing `gtfs_time_to_ts` macro is wrong for those few hours. Flagged in validation.
- **Mart history discontinuity** at cutover (new on-time definition) until the backfill is published.
- **Open:** D12 license reading (owner); the email address for alerts; whether to drop F3 orphans and backups (separate approval).
