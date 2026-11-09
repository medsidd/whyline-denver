# Operations and costs

This document separates **observed state**, repository configuration, and historical decisions. Refresh the observations before relying on them for an operational change. No deployment, scheduler change, or data refresh is implied by reading these commands.

## Verified October 26, 2026

| Surface | Readback |
|---|---|
| Public API | `/api/health` returned `status=ok`, `engine_default=duckdb` through both the site proxy and Cloud Run origin |
| Freshness metadata | BigQuery `2026-10-26 23:48 UTC`; DuckDB `2026-10-26 16:18 UTC` |
| Cloud Scheduler | `realtime-ingest` enabled, `*/15 * * * *`; `realtime-load` enabled, `2-59/15 * * * *` |
| Recent load executions | `realtime-load-fnvqs` and `realtime-load-pd7pd` each had one successful task, completed at 23:48 and 23:33 UTC |
| Nightly ingestion | [October 26 run](https://github.com/medsidd/whyline-denver/actions/runs/40341455035) succeeded |
| Nightly BigQuery | [October 26 run](https://github.com/medsidd/whyline-denver/actions/runs/40354713648) succeeded |
| Nightly DuckDB | [October 26 run](https://github.com/medsidd/whyline-denver/actions/runs/40357404073) succeeded |
| Latest code CI observed | [October 15 run](https://github.com/medsidd/whyline-denver/actions/runs/38734586593), commit `a723429`, succeeded |
| Workflow inventory | CI, three nightly workflows, and two manual realtime workflows reported active |
| Default GitHub branch | `main` |

The August 11 pause was superseded by the approved October restart. The system should not be described as paused based on that old handoff. This snapshot does not authorize changing the running schedules. Keep retained raw data and warehouses intact.

Freshness metadata and successful jobs do not prove source completeness, current model artifacts, or correct served results. The October 26 overview did not re-audit every mart, current NOAA availability, recent ingest executions, billing root causes, or Vercel deployment settings. Follow [QA validation](../QA_Validation_Guide.md) for those checks.

## Google Cloud spending snapshot

Queried directly from `whyline-denver.billing.gcp_billing_export_v1_010059_B03714_C2A403` on October 26, 2026, filtering `project.id = 'whyline-denver'` and usage dates in `America/Los_Angeles`. Net means `cost + SUM(credits.amount)`.

| October usage to date | USD |
|---|---:|
| Gross charges | 10.3012 |
| Credits | -3.2939 |
| Net charges | 7.0072 |
| BigQuery net | 6.5182 |
| Cloud Storage net | 0.2589 |
| Artifact Registry net | 0.2301 |
| Cloud Run net | 0.0000 (3.2939 gross offset by credits) |

Latest usage end represented: October 26 at 20:00 UTC (1 p.m. Pacific). Latest export timestamp: 23:54 UTC. Reporting can lag by service; neither timestamp proves all charges through that time have arrived. This is usage-period spending, not a finalized invoice, and project-filtered costs may exclude account-level charges.

Daily net costs rose from about $0.10 on October 19 to $1.05–$1.08 on October 21–25. That recent rate implies roughly $32 per 30 days **if sustained**, not a provider forecast. The increase has not been traced to individual jobs. BigQuery analysis was $5.4707 of the month-to-date total, BigQuery storage $1.0476. Do not infer those amounts from `INFORMATION_SCHEMA` byte estimates alone.

This covers Google Cloud export records only, not Vercel, domain registration, separately billed AI services, or future credit eligibility. Historical estimates elsewhere are engineering history, not current prices or a spending commitment.

### BigQuery job attribution, October 27, 2026

Read from `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT (the datasets are in the `US` multi-region, not `us-central1`), grouping dbt jobs by the `node_id` in their query comment. Billed bytes were steady at about 163 GiB per day from October 15 to 26, about $1 per day at the $6.25/TiB list price. That matches the billing export once the 1 TiB monthly free tier is accounted for.

| Source, October 20–27 | GiB/day | Share |
|---|---:|---:|
| `stg_rt_events` MERGE (96 runs/day, ~1.34 GiB each) | 130.5 | 80% |
| `int_headway_adherence` | 10.7 | 7% |
| Route-day and stop-hour marts | 9.4 | 6% |
| Minimum billing (10 MB per referenced table) on raw inserts, ingestion log, and small DDL | ~9 | 5% |
| All nightly work | ~5 | 3% |

Dry runs split each `stg_rt_events` run into: 892 MiB for its join to `int_scheduled_arrivals`, 251 MiB for the `stg_gtfs_trips` view (which rescans all 199 raw extracts), 186 MiB for the MERGE target key scan, and 41 MiB of new realtime data. `int_scheduled_arrivals` was last built on February 5, 2026 and covers service dates only through March 7, 2026, so that join matched no rows. No BigQuery queries from the NL-SQL app appeared; it defaults to DuckDB.

### Realtime cost fix deployment, October 27, 2026

[PR #60](https://github.com/medsidd/whyline-denver/pull/60) (merge `b2ffdba`) bounded the realtime inputs and added `int_scheduled_arrivals` to `nightly-bq`.

- Both realtime jobs were moved at 16:25 UTC from `whylinedenver-realtime@sha256:ffb2f017…5445b1b`, the rollback image, to `@sha256:67dcbd96…9494c50`. That image was built from a tree identical to the merge.
- At 16:35 UTC, `stg_gtfs_trips` was built as a table (21.8k rows) and `int_scheduled_arrivals` was rebuilt (18.7M rows, 9.7 GiB processed). Coverage is now 2026-09-27 through 2026-11-26.

Billed per `realtime-load` run:

| Model | 16:20 (old image) | 16:33 (new image, before rebuild) | 16:48 (after rebuild) |
|---|---:|---:|---:|
| `stg_rt_events` | 1,387 MiB | 314 MiB | 545 MiB |
| `int_headway_adherence` | 94 + 20 MiB | 0 + 20 MiB | 355 + 20 MiB |

All three runs succeeded. `int_headway_adherence` again writes current service dates.

The 16:48 costs were higher than projected because the schedule bounds were open-ended and the rebuilt schedule extends about 30 days ahead. [PR #61](https://github.com/medsidd/whyline-denver/pull/61) (merge `9717b00`) caps both reads at tomorrow.

Both jobs moved at 17:26 UTC to `@sha256:e54773d1…98d9a93b`, built from a tree identical to that merge. The 17:32 run succeeded:

| Model | 17:32 run |
|---|---:|
| `stg_rt_events` | 128 MiB |
| `int_headway_adherence` | 55 + 20 MiB |
| Whole run | ~383 MiB (about 1,690 MiB at 16:20) |

That projects to roughly 51 GiB per day including the nightly schedule rebuild, against 163 before.

A bounded duplicate check found about 96 duplicated `(feed_ts_utc, trip_id)` keys per day in `stg_rt_events` since at least October 20, predating this change. They are rows with null trip, route, and stop, re-inserted on each run within the 12-hour window because a MERGE never matches null keys. The reliability marts exclude them (null route or stop); the headway models and mart merges showed no duplicates. Remeasure seven days after PR #61 is deployed.

### Medallion and Kimball cutover, October 27, 2026

[PR #63](https://github.com/medsidd/whyline-denver/pull/63) (merge `51b46c3`) restructured dbt into silver (`stg_denver`), gold core (`core_denver`, new), and gold serving (`mart_denver`). See the [model reference](../../dbt/models/README.md).

**Bronze partitioning (17:50–18:10 UTC).** The ten snapshot tables (GTFS static, sidewalks, tracts, ACS) were copied into tables partitioned by `_extract_date` (`CREATE TABLE … LIKE`, so column modes and descriptions carried over), verified, and swapped in by rename.
- Verification: per-extract row counts matched on all ten; full-row checksums matched on the seven smaller tables. `raw_gtfs_shapes`, `raw_gtfs_stop_times`, and `raw_sidewalks` (76 GB) were checked by counts only, to avoid a ~$0.90 scan.
- The originals remain as `<table>__unpartitioned_bak`. Drop them only after approval.
- A constant extract filter now reads 42 MiB of `raw_gtfs_stop_times`; the old `(select max(...))` filter still reads 9,958 MiB because a subquery does not prune.

**Side-by-side build.** Everything was first built from bronze into `stg_denver_v2`, `core_denver_v2`, and `mart_denver_v2`, then checked:
- all 73 dbt tests;
- nightly and realtime selections run incrementally, with zero duplicate keys in every merge target;
- comparison with the live marts.

Defects this found in existing data, fixed in the PR:
- **Stale-schedule on-time.** Live route-day marts showed 100% on-time for January and April–August 2026 with 0% of delays resolved. The stale schedule left delays missing, and missing delays count as on-time. Rebuilt with the schedule current on each date: 83–87% resolved and about 77% on-time.
- **Misaligned GTFS loads.** The loader maps CSV columns by position, so reordered GTFS files loaded into the wrong columns: trips and calendar from 2025-12-09 to 2026-01-04, and routes on several days. Live `mart_gtfs_routes` listed 255 routes; it now lists 134. Silver flags rows that fail GTFS-format checks. The schedule only uses days on which every loaded file passed. All 400 dates from 2025-10-23 to 2026-11-26 now have a schedule.
- **Inflated sidewalk lengths.** `sidewalk_len_m_within_200m` was about 281× too large, because every sidewalk extract was summed. Access scores barely moved, since the inflation was uniform.
- **Nondeterministic crash counts.** 13,692 of 194,281 crashes have conflicting source rows, so crash counts near about 300 stops changed between builds. The latest extract now wins; two rebuilds produced identical checksums.
- **Duplicate silver rows.** Rows without a `trip_id` were re-inserted on every run; they are now dropped.

**Production switch (UTC).**

| Time | Step |
|---|---|
| 20:09 | `realtime-load` paused; `realtime-ingest` kept running |
| | #63 merged |
| 20:10–20:14 | Full rebuild of `staging core marts`: 34 models, about 40 GiB |
| | 73 tests passed |
| 20:19 | Both jobs moved to `whylinedenver-realtime@sha256:17042b45…f29e3`, built from a tree identical to the merge; rollback image `@sha256:e54773d1…98d9a93b` |
| 20:19 | `realtime-load` resumed |

The 20:32 and 20:47 runs succeeded.
- **Backlog:** the 20:32 run loaded the pause backlog, and all feeds from 20:00–20:31 are in silver.
- **Duplicates:** fact duplicate keys are zero.
- **Delays:** 95% of today's observations have a resolved delay.
- **Cost:** a steady run bills about 410 MiB, against about 383 MiB under Phase 1.

**Downstream.**
- **DuckDB:** marts were re-exported with `--force` from 2026-07-29, and the warehouse was refreshed and uploaded at 20:44 UTC using the merged code. It includes the appended columns.
- **API:** an image with regenerated artifacts is built (`whylinedenver-api@sha256:1f5c73f6…88adee57`, artifacts in [PR #65](https://github.com/medsidd/whyline-denver/pull/65)) but **not deployed**. The service still runs revision `whylinedenver-api-restart-20261014`. That revision works against the new marts, which keep their names and columns, but its schema brief does not list the new columns, and its `/filters/bigquery/stops` reads the now all-extracts `stg_gtfs_stops`. The dashboard does not call that endpoint.

**Nightly cost estimate.** About 5.6 GiB per night: the dimensions, a 3.9 GiB schedule refresh, and a 3.1 GiB crash fact. Before the cutover the nightly schedule rebuild alone was 9.7 GiB.

The cleanup this cutover left (the `*_v2` datasets, the ten bronze `__unpartitioned_bak` tables and the obsolete `stg_denver` objects) was done on October 29; see below.

### Realtime stop visits, October 28, 2026 (built, not deployed)

The continuous GTFS-RT poller, its four raw tables, `fct_stop_visit`, `fct_trip_status` and the backfill are built; see the [plan](plans/realtime-stop-visits.md). The poller and stream loading ([#69](https://github.com/medsidd/whyline-denver/pull/69)) merged on October 29 at 06:23 UTC (`d68f349`). The dbt models ([#70](https://github.com/medsidd/whyline-denver/pull/70)) and the mart cutover ([#71](https://github.com/medsidd/whyline-denver/pull/71)) stay drafts until their gates (plan §7 step 9 and §6). No cloud resource, table, image, job or schedule for the stream was created or changed. The owner runbook (plan §7) lists every command with its rollback, and the dual-run checklist (plan §6) gates the mart cutover.

Read-only findings that affect operations:
- The Compute Engine API is disabled on the project. Enabling it creates an auto-mode `default` network, which cannot do IPv6, so the runbook creates a custom VPC.
- `whylinedenver-raw` deletes every object after 180 days. GCS snapshots before about 2026-05-01 are gone; BigQuery raw is the only older copy, which is why the backfill reads it with `EXPORT DATA`.
- `raw_gtfsrt_trip_updates` is 41.70 GiB logical but 1.14 GiB physical. Physical storage billing on `raw_denver` would cut that table's storage cost about 18× (37× fewer bytes at twice the per-GiB price; optional, with a 14-day cooldown between changes).

Expected cost (plan §4): about $4 a month more at the 90-day raw cap in month 3 (logical billing), and realtime queries falling from about $2.4 to $0.45 a month after the cutover. The dual run adds roughly $2–2.5 over 10 days.

### Cleanup, October 29, 2026 (UTC)

With the owner's approval, ten orphaned objects were dropped at 06:31–06:32:
- `stg_denver` tables `int_scheduled_arrivals` (18.7M rows, 1.09 GiB), `int_headway_adherence` (2.85M rows, 184 MiB) and `int_headway_adherence_backup_20251109` (empty);
- `stg_denver` views `int_rt_daily_coverage`, `int_rt_events_resolved`, `int_stop_headways_observed`, `int_stop_headways_scheduled`, `int_weather_by_date` and `stg_rt_events_daily_stats`;
- `raw_denver.__tmp_gtfsrt_trip_updates_20260410183403_174a2a29` (9,660 rows), left by a failed April load.

Checks before the drop:
- none had changed since 20:05 on October 27, before the #63 switch;
- no current dbt model builds them, and no code references them;
- in every dataset's `INFORMATION_SCHEMA.VIEWS`, only the dropped views referenced them.

`stg_denver` now holds only the 12 current silver models. Their model SQL is in git history: `76d05be^` for `int_rt_daily_coverage` and `stg_rt_events_daily_stats`, `3c213cd^` for the rest. Time travel can restore the tables until November 5 at 06:31, for example `bq cp whyline-denver:stg_denver.int_scheduled_arrivals@1793255500000 whyline-denver:stg_denver.int_scheduled_arrivals`; views must be recreated from their SQL. The pre-#63 rollback image (`@sha256:e54773d1…98d9a93b`) read `int_scheduled_arrivals`, so it can no longer run without that restore.

### Warehouse overwritten by local test runs, October 28–29, 2026 (UTC)

`tests/sync/test_refresh_duckdb.py` built real `Settings`, whose defaults name the production bucket, and ran the refresh with uploads on. On a machine with `.env` and application-default credentials, each `make test` replaced `gs://whylinedenver-raw/marts/duckdb/warehouse.duckdb` with a test file and merged test marts into `state/sync_state.json`. CI was unaffected because it has no credentials.

- **When:** ten local runs between 16:36 on October 28 and 01:11 on October 29. The bucket keeps object versions, so each run is visible. Older sync-state versions carry the same pollution (`mart_hot`, `mart_cold`).
- **Effect:** from 16:36 until the repair, `/api/downloads/warehouse` served a 268 KiB file holding one view that pointed at a laptop temp path, and the DuckDB freshness showed the last test run. Dashboard queries and CSV downloads use BigQuery and were not affected. No other object under `marts/` was written during those runs, and `raw/` holds no test-fixture paths.
- **Last good versions:** warehouse generation `1793204111822838` (16:15, from the Nightly DuckDB run; all nine marts); sync state generation `1793205237527316` (16:33).
- **Fix:** a suite-wide fixture now makes cloud client constructors raise (see [testing](TESTING.md)).
- **Repaired at 08:07 on October 29, with the owner's approval:**
  - the last good warehouse version was copied back over the live object (new generation `1793261235195494`);
  - the sync state was rewritten with its last good `duckdb_synced_at_utc` and mart dates. The test entries (`mart_hot`, `mart_cold`) were dropped and the current BigQuery timestamp kept.
  - The public download now returns the 6.8 MB warehouse (MD5 `3236e24d…`), and DuckDB freshness reads 10:15 MDT on October 28.
  - The next Nightly DuckDB run refreshes both as usual.


### Backups and side-by-side datasets dropped, October 29, 2026 (UTC)

With the owner's approval, these were dropped at 08:20:
- the ten bronze `__unpartitioned_bak` tables, about 78 GB in all. The largest were `raw_gtfs_stop_times` (38.2 GB), `raw_gtfs_shapes` (26.9 GB) and `raw_sidewalks` (11.3 GB).
- the `stg_denver_v2`, `core_denver_v2` and `mart_denver_v2` datasets: 34 objects, about 16 GB, last created October 27.

Before the drop, no view in the live datasets referenced them and no code outside the docs named them. Time travel can recover them until November 5 at 08:20, for example `bq cp whyline-denver:raw_denver.raw_gtfs_stop_times__unpartitioned_bak@1793262042000 …`; a dataset is undeleted with `bq undelete`.

### Stream deployment, October 29, 2026 (UTC)

Following plan §7, with the owner's approval. The owner ran steps 4, 6 and 7, because the agent's permission check blocks IAM changes and job updates.

| Step | State |
|---|---|
| 0 Rollback digests | both jobs were on `whylinedenver-realtime@sha256:17042b45…f29e3` |
| 1 Compute Engine API | enabled. It created the auto-mode `default` network, which nothing uses. |
| 2 Archive bucket | `gs://whylinedenver-rt-archive` (Coldline, us-central1, uniform access, public access prevented) |
| 3 Staging lifecycle | 7-day delete for `raw/rtd_gtfsrt_stream/`, plus deletion of that prefix's noncurrent versions after a day. The bucket keeps object versions, and the 180-day rule alone would leave them forever. |
| 4 Service account | `rt-stream-poller` with the four roles in the runbook |
| 5 Network | `whyline-rt`, subnet `whyline-rt-usc1` (external IPv6 `2600:1900:4000:485::/64`, Private Google Access), firewall rule `whyline-rt-iap-ssh` |
| 6 Image | both jobs on `@sha256:f049144d…c2f7d1` (built from `fa47a7d`) since about 08:35; the 08:47 `realtime-load` was the first run on it |
| 7 VM | `rt-stream-poller` created at 08:37:45; container started at 08:41 over IPv6 |
| 8 Verify | heartbeat every 5 minutes. First window `snapshot_at=2026-10-29T08:30`; archive tar and static zip in the archive bucket. The 08:47 `realtime-load` created the four raw tables (day or hour partitions, 90-day expiry, clustered on `route_id, trip_id`). |
| 9 dbt models | #70 merged at 08:56 (`85d3a7c`). The nightly run that started at 15:57 built them: 41 models passed; `fct_stop_visit` 88.4k rows, `fct_trip_status` 2.1k. Tests: 83 passed and 1 warning, 23 visits whose arrivals don't rise with stop sequence. Image `@sha256:12384b64ebcb072f1c4e496cda827aae62c4b600820094f76852a44cf46f4ea1` is built from `85d3a7c`; **until both jobs use it, the stream facts refresh only nightly**. |
| 10 Alerts | email channel for the owner; log metric `rt_stream_heartbeat`, counting only `cos_docker` lines because COS writes each container line to two logs; policies for a stale or missing stream and for a missing heartbeat |

First readings, which are not yet dual-run results:
- On October 29, 73% of timed visits were `shape_crossing` (within 30 s), 23% `shape_crossing_gap` (98 s average window) and 1.4% `last_prediction`.
- Poller peak RSS was 251 MB with 770 open trips at 16:50, against the 250 MB target, on a 1 GB e2-micro.
- The poller swapped to a new static feed (MD5 `bc44693f…`) during the day.
- The scheduled Nightly BigQuery run started at 15:57, almost 7 hours after its 09:00 cron; GitHub delays scheduled workflows under load.

The dual run (plan §6) starts with these partitions. Earliest cutover review: November 5, after a weekend.

Physical storage billing (decision 6) was deferred until after a week of real pipeline runs, so it could be judged on billed costs. The owner chose it on November 5.

`whylinedenver-raw` keeps every overwritten or lifecycle-deleted object as a noncurrent version, with no rule that removes them (for example, 151 versions of the DuckDB warehouse). That is unmeasured storage cost worth reviewing alongside the billing decision.

### Weather history for the DIA station, October 30, 2026 (UTC)

The weather station changed from `USW00023062` to the DIA station `USW00003017` in `3d8a245`, but history was never re-fetched for DIA.

- **What was found:** `fct_weather_daily` had DIA rows only from 2026-09-15. The route-day mart joins on the configured station, so in the last year 33,245 of 34,820 route-days had no weather, and none was marked as a snow day. Every weather comparison before mid-September was empty.
- **What was done:** NOAA CDO returned complete DIA history: 622 days from 2025-01-01 to 2026-09-14, with no missing precipitation and 37 snow days. It was loaded at 18:08 into `raw_weather_daily`, from `gs://whylinedenver-raw/raw/noaa_daily/extract_date=2026-09-14/station=USW00003017/weather.csv.gz`. The ingestor now splits NOAA requests into year-long ranges, and sends dates older than six days to Open-Meteo's archive.
- **Done (owner, 2026-11-02 about 22:00 UTC):** rebuilt the route-day history with `--vars '{route_day_window_days: 400}'`, running `fct_weather_daily`, `mart_reliability_by_route_day` and `mart_weather_impacts`. Afterwards, 127 of 28,006 route-days in 2026 had no weather, all of them today (2026-11-02), whose weather arrives the next night, against 33,245 of 34,820 before. Every 2025 route-day has weather, and 14 snow days are marked (3 in 2025, 11 in 2026). The command, for any later rebuild:

```bash
cd /Users/medsidd/dev/whyline-denver && PYTHONPATH=$PWD/src DBT_PROFILES_DIR=$PWD/dbt/profiles GCP_PROJECT_ID=whyline-denver BQ_DATASET_RAW=raw_denver BQ_DATASET_STG=stg_denver BQ_DATASET_CORE=core_denver BQ_DATASET_MART=mart_denver .venv/bin/python -m tools.dbt_with_env run --project-dir dbt --target prod --select fct_weather_daily mart_reliability_by_route_day mart_weather_impacts --vars '{route_day_window_days: 400}'
```

Run it from the repository root. Since the stop-visit cutover it only rebuilds stop-visit partitions, because the legacy models are disabled. A local dbt run rewrites the tracked `dbt/target` artifacts; restore them with `git checkout -- dbt/target` unless a release is regenerating them on purpose.

### Metrics facts and the alerts and Veo image, November 2, 2026 (UTC)

These [metrics plan](plans/metrics-implementation.md) work packages merged: WP1 [#78](https://github.com/medsidd/whyline-denver/pull/78), WP2 [#79](https://github.com/medsidd/whyline-denver/pull/79), WP3 [#80](https://github.com/medsidd/whyline-denver/pull/80), WP4 [#81](https://github.com/medsidd/whyline-denver/pull/81), WP5 [#82](https://github.com/medsidd/whyline-denver/pull/82) and the edge-case fix [#85](https://github.com/medsidd/whyline-denver/pull/85).

- **What builds:** six core facts and nine marts, built by the nightly `staging core marts` run only; the 15-minute realtime selection is unchanged.
  - Facts: `fct_prediction_accuracy`, `fct_trip_occupancy`, `fct_stream_health`, `fct_stop_headway` and `fct_segment_traversal`.
  - All new marts are `allow_in_app: false`, so the app, exports and DuckDB are unchanged until release R1.
- **Cost:** the first build starts at 2026-10-29 and reads about 2.5 GB, mostly `fct_prediction_accuracy` (1.37 GB). After that, about 1.9 GB a night, or 57 GB a month, inside the free 1 TiB.
- **Raw expiry:** `fct_prediction_accuracy` and `fct_trip_occupancy` have full refresh disabled, because their raw inputs expire after 90 days.
- **Check after the first nightly run:** every new model passed and its tests ran. Then this read-only count should show one row per service date from 2026-10-29:

```bash
bq query --use_legacy_sql=false --project_id=whyline-denver \
  'select service_date, count(*) n, countif(has_prediction) n_pred from `whyline-denver.core_denver.fct_prediction_accuracy` group by 1 order by 1'
```

**Alerts and Veo image (owner):** WP8 [#83](https://github.com/medsidd/whyline-denver/pull/83) and WP14 [#84](https://github.com/medsidd/whyline-denver/pull/84) add two ingestors to the `realtime-load` entrypoint. Each run snapshots RTD service alerts and Veo vehicles before the load, and a failure logs `ALERTS_INGEST_FAILED` or `VEO_INGEST_FAILED` without stopping the load.

- **Image:** `whylinedenver-realtime@sha256:c3fc67337b0ac6af6649ea2df4d2f6b74aa8d2184382ca667244a0854e57b459`, built with Cloud Build from `80e3cfc` (tag `80e3cfc`). The edge-case fix merged after it touches only nightly dbt models.
- **Deployed:** the owner moved both jobs to this image at about 17:45 UTC on 2026-11-02. The 17:47 `realtime-load` run was the first on it: it snapshotted 62 alerts and 8,147 Veo vehicles, created `raw_gtfsrt_alerts`, `raw_gtfsrt_alert_periods` and `raw_gbfs_veo_vehicles`, and succeeded.
- **Rollback:** the previous image is `@sha256:12384b64ebcb072f1c4e496cda827aae62c4b600820094f76852a44cf46f4ea1`. The commands used, with that digest swapped in for a rollback:

```bash
IMAGE=us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime@sha256:c3fc67337b0ac6af6649ea2df4d2f6b74aa8d2184382ca667244a0854e57b459
gcloud run jobs update realtime-load --project=whyline-denver --region=us-central1 --image="$IMAGE"
gcloud run jobs update realtime-ingest --project=whyline-denver --region=us-central1 --image="$IMAGE"
```

- **Verify after the next load:**
  - `gcloud storage ls gs://whylinedenver-raw/raw/rtd_gtfsrt_alerts/ gs://whylinedenver-raw/raw/gbfs_veo/ | tail -4` shows new snapshots.
  - The first load creates `raw_gtfsrt_alerts`, `raw_gtfsrt_alert_periods` and `raw_gbfs_veo_vehicles`.
  - Search the job logs for `ALERTS_INGEST_FAILED`, `VEO_INGEST_FAILED` and `VEO_FEED_SUSPECT`.
- **What follows:** the alerts and micromobility dbt models come once data has landed, so no nightly run references a missing table. Veo's feed publishes no licence, so its marts wait for a terms check before publication.

### Nightly runs triggered by hand, November 2, 2026 (UTC)

At the owner's request, the three nightly workflows were run by hand. Overlapping runs now queue instead of running together ([#92](https://github.com/medsidd/whyline-denver/pull/92)).

| Run | Commit | Result |
|---|---|---|
| Nightly ingest, 17:50 (a late scheduled run at 17:31 had already fetched everything) | `1a72943` | Success. The new reference layers, NTD and hourly weather loaded at 17:39 into `raw_arcgis_reference`, `raw_ntd_monthly` and `raw_weather_hourly`. |
| Nightly BigQuery, 17:52 | `1a72943` | 57 models passed; 136 of 137 tests passed and 1 warned (the known `assert_stop_visit_arrivals_monotonic`, 93 visits). First builds: `fct_prediction_accuracy` 5.66M rows (1.39 GB), `fct_trip_occupancy` 1.13M, `fct_stop_headway` 1.11M, `fct_segment_traversal` 0.67M. The run billed 15.4 GB in all. |
| Nightly DuckDB, 18:03 | `1a72943` | Success |
| Scheduled BigQuery 19:20 and DuckDB 19:40 | `e5be11b` | 72 models and 155 of 156 tests passed (the same warning). |
| Nightly BigQuery, 21:29 | `63dc4c2` | 78 models and 166 of 167 tests passed (the same warning). |
| Nightly DuckDB, 21:37 | `63dc4c2` | Success |

**Cost finding:**
- Billed dbt bytes are about 50–60 GB a day, mostly the 96 `realtime-load` runs. That's roughly 1.6 TB a month, over the free 1 TiB. (Understated: the November 5 review measured 74–107 GB a day across all jobs.)
- The largest nightly model is `fct_crash`, at 3.8 GB a night.

**Crash fix ([#100](https://github.com/medsidd/whyline-denver/pull/100)):** the owner chose to keep only crashes inside Denver's five-year window, so `stg_denver_crashes` now reads only the latest extract. That also fixed double counting.
- **The defect:** Denver re-numbered crashes between extracts (`2023163372` against `DP2023163372`), so the merged view held 194,547 crashes against 87,526.
- **Published counts:** 250 m crash counts were 13% high (69,029 against 60,910). Priority-hotspot ranks shift with the fix.
- **Cost:** bytes don't fall, because `raw_crashes` is partitioned by event date. Re-laying it out by `_extract_date` would save about $0.70 a month, so it's left alone.

**For the November 5 review:** route 15 has 43% of measured visits on time and 51% more than 5 minutes late, with a median delay of 570 s in the evening and 680 s at night. RTD reports about 84% local on-time performance. RTD measures at timepoints, but the gap is large enough to check trip matching for frequent routes before #71 publishes visit-based reliability.

### Second hand-triggered cycle, November 2, 2026 (UTC)

At the owner's request, the nightly workflows were run again after the crash fix ([#100](https://github.com/medsidd/whyline-denver/pull/100)), the scorecards ([#98](https://github.com/medsidd/whyline-denver/pull/98)) and RTD's reported figures ([#102](https://github.com/medsidd/whyline-denver/pull/102), [#103](https://github.com/medsidd/whyline-denver/pull/103)).

| Run | Commit | Result |
|---|---|---|
| Nightly ingest, 22:15 | `f51d857` | Success |
| Nightly BigQuery, 22:17 | `f51d857` | 80 models and 170 of 171 tests passed (the known `assert_stop_visit_arrivals_monotonic` warning, 103 visits). The export took 20 minutes instead of about 3, because the owner's weather rebuild had changed every route-day partition, and each changed partition is re-exported. |
| Nightly DuckDB and ingest, 22:47 | `0a371e1` | Success. The ingest loaded RTD's reported figures (340 values from 40 reports) into the new `raw_rtd_reported_performance`. |
| Nightly BigQuery, 22:53 | `33781ea` | 83 models and 172 of 173 tests passed (the same warning, 108 visits). |
| Nightly DuckDB, 23:06 | `33781ea` | Success |

After this cycle:
- `fct_crash` holds 87,526 crashes, and the published 250 m crash total is 60,910 (it was 69,029).
- The scorecards cover 8,155 stops and 134 routes.
- `mart_reported_vs_measured_by_month` has RTD figures for 20 months × 4 services, and WhyLine measurements for October and November 2026; none overlap yet.
- `fct_micromobility_near_stop` stays empty until the first complete local day, 2026-11-02, builds in the next nightly run.

### Veo availability validated, November 2, 2026 (UTC)

[#105](https://github.com/medsidd/whyline-denver/pull/105) lets `fct_micromobility_near_stop` build today so far, rather than complete days only. The owner asked for the nightly runs again to fill it: ingest (23:21), BigQuery (23:23, 83 models, 172 of 173 tests, the known warning) and DuckDB (23:35), all successful.

| Check | Result |
|---|---|
| Raw snapshots since the image update | 23 from 17:49 to 23:17 UTC, 13 to 16 minutes apart, each loaded once. 8,135–8,206 vehicles per snapshot (7,622–7,880 available), all inside the RTD box, no unknown vehicle types. |
| Load job | All 25 recent `realtime-load` runs succeeded; no `VEO_FEED_SUSPECT`, `VEO_INGEST_FAILED` or `ALERTS_INGEST_FAILED` in the logs. |
| Fact grid | 37,898 rows = 2,707 Denver stops × 7 local hours (10:00–16:00 MST) × 2 form factors. The stop set equals `bridge_stop_street_safety`'s. |
| Snapshots per hour | Equal to the raw count for every complete hour (4). Hour 16 had 2 at build time, and fills in on the next run. |
| Independent recomputation | For 60 stops × 2 form factors at 12:00, counts recomputed straight from raw with `ST_DWITHIN` matched the fact exactly (average and share with none). |
| Value checks | Averages ≥ 0 and shares between 0 and 1; an average of 0 if and only if every snapshot had none; the dbt unique and accepted-values tests pass. |
| Mart | 5,414 rows = 2,707 stops × weekday × midday and PM peak, so far. On average there are 3.0 scooters and 3.8 bikes within 200 m; 34% of the time no scooter is nearby, and 29% no bike. |

The highest counts are at Larimer St & 26th St in RiNo (38 scooters and 26 bikes at midday) and at W 10th Ave & Decatur St (34 and 27). The second looks like a Veo staging or charging site, and is worth a look before publication.

### Weekly job access workflow, November 2, 2026 (UTC)

`.github/workflows/weekly-access.yml` (WP12) runs on Mondays at 06:00 UTC and can be dispatched by hand. It:
1. installs Java 21, `osmium-tool` and `r5py==1.1.7`;
2. downloads Geofabrik's Colorado extract (about 390 MB), clips it to the RTD box, and downloads RTD's GTFS;
3. routes the RTD-county tracts in four windows;
4. writes `raw/job_access/extract_date=<day>/` and loads that day's files into BigQuery.

It uses the same repository secrets as the nightly ingest. It doesn't change any Cloud schedule. A run takes about 10 to 20 minutes of a free public-repository runner. It needs about 12 GB of Java heap; the runner has 16 GB.

### Job access, bus lanes and spikes, November 3, 2026 (UTC)

- **Weekly job access ([#109](https://github.com/medsidd/whyline-denver/pull/109), [#111](https://github.com/medsidd/whyline-denver/pull/111)):** the first `weekly-access.yml` run was dispatched at 00:08 and succeeded in about 10 minutes.
  - Geofabrik's Colorado extract (387 MB) was clipped to 120 MB, and routing took about 1 minute per window.
  - It created `raw_job_access` with 9,360 rows.
  - The scheduled run is Mondays at 06:00 UTC.
- **Bus lanes ([#108](https://github.com/medsidd/whyline-denver/pull/108)):** `bridge_segment_transit_lane` has 115 segment-lane pairs on 8 corridors. No before-and-after is possible yet: every lane predates the data.
- **Spikes ([#110](https://github.com/medsidd/whyline-denver/pull/110)):** findings are in [metrics spikes](plans/metrics-spikes.md). Nothing is ingested.
- **Nightly runs:** BigQuery at 00:27 (`e7eeb4a`): 88 models and 179 of 180 tests passed, with the known monotonic-arrivals warning (113 visits). DuckDB at 00:42 succeeded.
- **Results:** `mart_job_access_by_tract` has 3,120 rows (780 tracts × 4 windows), and the stop scorecard carries job access for 3,275 stops.

### Dual-run review, November 5, 2026 (UTC)

The review the [plan](plans/realtime-stop-visits.md) §6 asks for. It covers service dates 2026-10-30 to 2026-11-04, plus 2026-10-29 where noted. Everything was read-only except a local replay; the 15-minute snapshot job still runs. **Recommendation: approve the cutover (#71), with the two caveats at the end.** The owner hasn't approved it yet.

| Check (§6) | Result | Verdict |
|---|---|---|
| 1. Completeness | 96.6–97.8% of scheduled stop events seen each day; 96.9–97.8% excluding canceled trips | Pass |
| 2. Accuracy | 74–75% of arrivals within 30 s; bus 74.8%, light rail 78.0%, commuter rail 36.7% | Pass; commuter rail stays flagged |
| 2. Against GPS, routes 15 and 15L, Nov 3 | 98% of 12,463 crossings within 60 s of the closest GPS report | Pass |
| 2. STOPPED_AT, Nov 3 | Arrival at or before the first STOPPED_AT: 95.3% at middle stops (1.7% over 30 s late); 82.0% at last stops (13.3% over 30 s late) | Pass at middle stops; last stops are weaker |
| 2a. Route 15 lateness | Real lateness, not trip mismatching (below) | Pass |
| 2a. RTD's October figure | RTD's latest report is August | **Can't run yet** |
| 3. Old vs new | Every difference is an intended change or a fixed defect (below) | Pass |
| 4. Determinism | Full replay of Nov 3: 335,698 of 335,698 visits present; 331,993 of 331,997 arrivals identical | Pass |
| 5. Cost | The new pipeline bills about the same as the old one; removing the old one saves about 26 GB a day | Pass |

**Stream health:** all 96 windows were healthy on every full day from October 30 to November 3. The DST change on November 1 shows no shift in delays.

**Completeness:** 1,540 of 23,666 route-hours (6.5%) fell below 90%, holding about 21,400 of the 1.82M scheduled stop events. By main cause:

| Main cause | Route-hours | Explanation |
|---|---|---|
| RTD marked the stop skipped | 427 | 7,444 of 7,468 skipped visits on Nov 3–4 are at stops named in an RTD alert at some point; on route 15 they repeat at the same three stops every day |
| Partial trip | 329 | Reports stop part-way; see the N Line below |
| No vehicle reported | 322 | Trip is in the feed, but no vehicle ever reports on it |
| Stop missed on a completed trip | 220 | 1,139 events, 0.06% of the schedule; the only group that could be an engine gap |
| Never in either feed | 119 | Almost all rail: 101E, 101C and 117N |
| Canceled | 88 | RTD canceled the trip |
| Vanished after running | 35 | The vehicle left the trip early |

Route 117N, the N Line, is the outlier at 25%. Its trains stop reporting part-way along the line: train `117N_2` last reported at 13:12:35 on Nov 3, about 11 km into a 22 km trip, and no later report exists in the raw feed. That comes from the feed rather than the engine. `pct_observed` shows it, so its figures need that caveat.

**Route 15:** on-time was 48% over six days and 43.6% on Nov 3. These checks agree that this is real:
- **GPS:** on-time computed from the closest GPS report to each stop is 43.1%, against 43.6% from the engine (15L: 41.6% against 42.0%).
- **Vehicle matching:** 4,629 of 4,642 trips on the frequent routes tested had one vehicle. Terminal trip switches are 0.2% of route 15 visits, and removing them fleetwide raises on-time by 0.08 points.
- **Run times:** median run time exceeds the schedule on both: 15 takes 61.6 minutes against 59.1, and 15L takes 64.7 against 58.5 (Nov 2–4).
- **Growth along the line:** median delay rises from 72–126 s at the first stop to 370–560 s at the far end.
- **Schedule:** the fact's scheduled times match `fct_scheduled_stop_time` on all 18,268 visits checked.

**Old vs new:** fleet on-time falls from 88–92% to 74–77%, and 119 of 120 routes go down. Applied to the new visits, the old window gives 86.5% and RTD's gives 74.7%, so about 12 points come from counting arrivals over a minute early as not on time. The rest comes from sampling terminal arrivals and from counting unknown delays as on time.
- **Largest drops:** AL (89.0% to 31.1%) and FREE (98.5% to 57.2%). Both run ahead of schedule: AL reaches its last stop a median 10 minutes early, and FREE a median 44 s early at middle stops with buses minutes apart. Early running is real, but a low figure misdescribes a turn-up-and-go shuttle. `mart_wait_by_route_day` is the better measure for these.
- **Grain:** 740,253 stop-hour rows, all unique, with no NULL on-time values.
- **Coverage:** two route-days on Nov 1 exist only in the old mart; they weren't investigated.

**RTD comparison:** the gap is in bus only. WhyLine's October 29 to November 4 figures against RTD's August figures:

| Service | WhyLine | RTD |
|---|---|---|
| All bus | 73.5–75.2% | 83.3% |
| Light rail | 84.6–88.1% | 89.8% |
| Commuter rail A/B/G | 93.0–94.3% | 95.0% |

Restricting Nov 3 to GTFS timepoints and using departures where known moves bus from 70.9% (arrivals) to 73.3%, or 78.0% on the 38% of timepoint visits with a recorded departure. That narrows the gap without closing it. The months and methods still differ, so the remaining 5–10 points are unexplained.

**Cost:**
- **Correction:** the "50–60 GB a day" in the November 2 notes counted dbt models only. The project billed 74–80 GB a day from October 30 to November 1 and about 90–107 GB a day on November 3–4, including manual work. At about 90 GB a day that's 2.7 TB a month, about $9 over the free tier.
- **Old vs new, October 29 to November 4:** the old pipeline (`stg_rt_events`, `fct_trip_observation`, `fct_stop_arrival` and two raw loads) billed 183 GB, about 26 GB a day. The new one (`fct_stop_visit`, `fct_trip_status` and four raw loads) billed 157 GB, about 22 GB a day.
- **After cutover:** about 64 GB a day, or about $5 a month over the free tier.

**Storage billing (decision 6):** `raw_denver` is 150.2 GB logical and 7.7 GB physical, because `raw_gtfsrt_trip_updates` alone is 46.8 GB against 1.3 GB. That's about $2.60 a month logical against about $0.30 physical at list price, and the gap grows with the raw stream. Recommendation: switch.

**#71 readiness:** a trial merge onto main conflicts only in `AGENTS.md`, `dbt/models/README.md` and `docs/diagrams/data_model_overview.mmd`. `dbt parse` and the test suite pass on the merged tree. Rendered as read-only SELECTs, both marts run; the route-day read is 157 MB and the stop-hour read 188 MB for a seven-day window.

**Caveats if approved:**
1. Published fleet on-time drops about 14 points on cutover, and bus stays 5–10 points below RTD's figure. The glossary and app note must say so.
2. Compare with RTD again when its October report appears, likely around the end of the year. Until then, the bus gap is unexplained.

### Cutover approved and physical storage billing, November 5, 2026 (UTC)

The owner approved the cutover after the review above, and chose physical storage billing.

- **Storage billing:** `raw_denver` moved from logical to physical at 11:56 UTC. The setting can't change again for 14 days, so November 19 at the earliest. Rollback: `bq update --storage_billing_model=LOGICAL whyline-denver:raw_denver`.
- **Found while merging #71 with main:**
  - **First day:** any rebuild would have replaced October 28's full legacy partitions (128 routes, 48,551 events on route-day) with the stream's 107 visits on 6 routes. Both marts now leave out service dates before `stream_first_full_date`.
  - **Windows across the cutover:** `mart_weather_impacts` and `mart_priority_hotspots` averaged 30 and 35 days, which would have mixed the two methods. Both now read stop-visit days only, so they start with about a week of data.
  - **On-time boundary:** seven newer marts counted exactly 60 s early as on time, unlike the reliability marts and RTD's "less than one minute early". All now use `-60 < delay <= 300`.
  - **Freshness:** `raw_gtfsrt_trip_updates` and `raw_gtfsrt_vehicle_positions` no longer have freshness checks, because they freeze when `realtime-ingest` pauses.

### Cutover deployed, November 6, 2026 (UTC)

The owner ran the three cutover steps between about 17:29 and 17:32 UTC.

1. **Image:** both jobs moved to `whylinedenver-realtime@sha256:64d6be93347a32e573fa01a550135f6ba5f4e5eae08db3198aa42ab635bb7e25`, built with Cloud Build `f54e043a` from `bba4715` (tag `bba4715`). The last run on the old image (17:17) finished at 17:20, before the rebuild, so nothing rewrote the rebuilt days with the old method.
2. **Rebuild:** `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`, `mart_weather_impacts` and `mart_priority_hotspots`, with 30-day windows, at 17:30–17:31. All four passed in 59 s, processing about 265 MiB.
3. **Snapshot job paused:** the `realtime-ingest` scheduler is `PAUSED`; `realtime-load` stays enabled.

**Verified:**
- **Boundary:** October 26–28 are unchanged in both marts, with `data_version` NULL and built on November 4 (route-day) or October 30 to November 1 (stop-hour). October 28 still has 128 routes and 48,551 events on route-day, and 4,080 rows and 46,078 events on stop-hour. The 17:43 nightly rebuild left them unchanged too.
- **Stop visits:** October 29 to November 6 are all `stream_v1` in both marts, and the two marts agree on events for every day. November 3 has 331,997 visits, matching the replay in the review. Fleet on-time on full days is 73.0–76.9%.
- **First run on the new image:** `realtime-load-49lbh` (17:32) succeeded. It snapshotted 80 alerts and 8,205 Veo vehicles, built the six models of the stop-visit selection, and updated the freshness timestamp.
- **Cost per realtime run** (`INFORMATION_SCHEMA.JOBS_BY_PROJECT`, billed): 509–548 MiB on the new image against 714–753 MiB on the old one that afternoon. That's about 19 GB a day less. The 10 MB minimum per query is most of the gap between billed and processed bytes.
- **Re-export:** a hand-triggered Nightly BigQuery ([run 42263388383](https://github.com/medsidd/whyline-denver/actions/runs/42263388383)) built 85 models and passed 175 of 176 tests; the warning was the known `assert_stop_visit_arrivals_monotonic` (138 visits). It re-exported the 9 rebuilt partitions (October 29 to November 6) of each reliability mart. Nightly DuckDB ([run 42265450843](https://github.com/medsidd/whyline-denver/actions/runs/42265450843)) then refreshed both marts and succeeded.

**Rollback:**

```bash
IMAGE=us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime@sha256:c3fc67337b0ac6af6649ea2df4d2f6b74aa8d2184382ca667244a0854e57b459
gcloud run jobs update realtime-load --project=whyline-denver --region=us-central1 --image="$IMAGE"
gcloud run jobs update realtime-ingest --project=whyline-denver --region=us-central1 --image="$IMAGE"
gcloud scheduler jobs resume realtime-ingest --project=whyline-denver --location=us-central1
```

The old image builds the legacy models, which main has disabled, so a rollback also needs a revert of #71. The rebuilt partitions can't be restored to the old method.

### Release R1 API image, November 6, 2026 (UTC)

[#115](https://github.com/medsidd/whyline-denver/pull/115) publishes eight stop-visit marts and three ready-made questions ([metrics plan](plans/metrics-implementation.md), R1). The API image was built from its head commit, before merging, because the frontend deploys on merge.

- **Image:** `whylinedenver-api@sha256:2efd070f348ea4c4eaf2747686caf5264b473ed0affed9e9e859964f6505d4b1`, Cloud Build `32b2dc8b`, tag `13ee8f9`. It carries the regenerated `dbt/target` (20 app marts) and WP0's query logging.
- **Deployed:** by the owner at about 18:35 UTC as revision `whylinedenver-api-00014-vnh`. The rollback image is `whylinedenver-api@sha256:1f5c73f6…88adee57` (revision `whylinedenver-api-00013-nr2`, from October 27).
- **Owner command:**

```bash
gcloud run services update whylinedenver-api --project=whyline-denver --region=us-central1 \
  --image=us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api@sha256:2efd070f348ea4c4eaf2747686caf5264b473ed0affed9e9e859964f6505d4b1
```

- **Then:** merge #115, then dispatch Nightly BigQuery and Nightly DuckDB to export the eight marts.
- **Check:**
  - `/api/models` lists 20 marts.
  - Each of the eight ready-made questions runs in the dashboard.
  - A query writes a `jsonPayload.event="query"` log line.

### Release R1 checked, tables validated and polished, November 6, 2026 (UTC)

**R1 is live.** These checks ran after the API deploy above:
- `/api/models` lists 20 marts, and all eight ready-made questions return rows through the API on BigQuery.
- #115 merged at about 18:37 (`41cc5d3`); Vercel deployed the dashboard.
- Nightly BigQuery ([run 42272533463](https://github.com/medsidd/whyline-denver/actions/runs/42272533463)) exported the eight new marts, and Nightly DuckDB ([run 42274730178](https://github.com/medsidd/whyline-denver/actions/runs/42274730178)) loaded them.
- Queries log `jsonPayload.event="query"` lines. About 40 queries on the `duckdb` engine between 19:27 and 19:29 UTC were this validation, not visitors.

**One failed request:** the first dashboard run after a cold start returned a Vercel 502 (`ROUTER_EXTERNAL_TARGET_CONNECTION_ERROR`). The request never reached Cloud Run, which had just started two instances, and the retry worked. Minimum instances is 0, so a cold start can drop a request; one warm instance would prevent it, at a cost. Not changed.

**Validation (read-only).** A profile of every column of the 32 marts and 29 core tables checked nulls, ranges, blanks, NaN and future dates, with the frozen legacy facts left out. Then 47 cross-checks ran:
- **Reliability:**
  - route-day and stop-hour visit totals match on every stop-visit day;
  - route-day events and on-time shares, recomputed from `fct_stop_visit`, match on all 1,094 route-days;
  - temperature bands agree with the day's low and high.
- **Identities:**
  - prediction visits = predictions + none, and padding = max(0, −p05);
  - trip outcomes add up to scheduled trips, and scheduled trips match `fct_scheduled_stop_time` for each day;
  - excess wait = expected − scheduled;
  - speed and run-time percentiles are ordered;
  - jobs within 30 ≤ 45 ≤ 60 minutes;
  - crash counts nest by distance and severity.
- **Coverage:** occupancy data on 83–88% of tracked trips each day.
- **Served copy:** row counts in the served DuckDB match BigQuery for 18 of the 20 app marts.
- **Expected, not defects:**
  - future dates in sample and routing dates and in alert periods;
  - negative countdowns ("due" predictions);
  - `difference_pct_on_time` all NULL until RTD publishes October;
  - `weeks_since_opening` all NULL;
  - dimension NULLs only on the Unknown members.

**Fixed in [#116](https://github.com/medsidd/whyline-denver/pull/116):**
- **Duplicate rows in the served DuckDB.** `EXPORT DATA` with `overwrite=true` replaces only the shards it writes. When an earlier export of the same partition wrote more shards, the extra ones stayed. The DuckDB refresh read both, so 78 route-day and 21 stop-hour export folders held stale copies, some from the legacy method. On November 6, 2026-11-04 had 255 route-day rows for 128 routes. The dashboard and downloads query BigQuery and weren't affected; the DuckDB warehouse and `engine: duckdb` API calls were. The exporter now deletes shards older than the export job after each export. Old folders keep their stale shards until re-exported (owner step 2 below).
- **A closure that ended before it began.** RTD stopped listing alert 85450 (a route 11 trip cancellation) at 21:17 UTC on November 2, three hours before the trip's 00:23–02:12 period. The 15-minute cutoff then gave it an end before its start, on 44 stop rows. The trip was in fact canceled. A period that begins after its alert left the feed now keeps RTD's own end.
- **Small stops ranked first.** The ready-made equity question ranked stop 35216 first (unreliability 100) on six RX arrivals, all 9–15 minutes early at a downtown drop-off stop.
  - The priority mart now weights stop-hours by measured visits. On November 6, 7,440 stops had a score; the weighted score differs from the hour average by 1.1 points on average.
  - It needs 30 measured visits in its 35-day window; 153 stops fall short.
  - The ready-made question now reads the mart's score instead of recomputing it.
- **Tests:** seven nightly invariant tests now guard these identities: prediction visits and padding, crowding shares, excess wait, segment percentiles, closure order, job-access thresholds, and route-day = stop-hour totals. The closure test fails on the current table until the next nightly rebuild; the rebuilt SQL gives 0 failing rows.

**Found, not changed:**
- **Sidewalk fields:** Denver's sidewalk layer has no values in `SIDEWALKSTATUS`, `SURFACE` or `BUILTYEAR` (0 of 190,234 segments), so `status`, `material` and `year_built` are always NULL. Since November 7, the city's asset inventory supplies condition, width and missing sidewalk instead (below).
- **Out-of-region stops:** `mart_gtfs_stops` includes 21 out-of-region stops in RTD's feed, such as Glenwood Springs, Vail and Colorado Springs.
- **Drop-off-only stops:** RTD may run early at stops where nobody boards. Counting early arrivals at drop-off-only stops (`pickup_type = 1`) as on time would raise November 3 bus on-time from 73.2% to 73.8%. That explains little of the 5–10 point gap with RTD's own bus figures. The rest is explained on November 7 (below).
- **Skipped stop:** RTD marked Eldora Mountain Resort (18032) skipped on all 89 visits since October 29.

**Polish:**
- **Descriptions:** every column of every enabled model now has a description: 1,019 columns in 85 models, 678 of them new. `persist_docs` copies them to BigQuery on each build. The 19:47 hand-triggered nightly showed that it sets a table's own description only when dbt creates the table, so the 18 incremental models, created once, had none. A post-hook (`persist_table_description`) now sets it on each incremental build ([#117](https://github.com/medsidd/whyline-denver/pull/117)). The 15-minute realtime job runs its own image (`bba4715`), which doesn't carry the setting. Its two staging views (`stg_rt_stop_visits`, `stg_rt_trip_status`) are re-created every 15 minutes, so they lose their descriptions until the next realtime image. Its tables keep theirs.
- **Dashboard:**
  - shares show as percentages in tables, chart axes and tooltips;
  - chart titles are readable;
  - the missed-trips and crash questions now get a chart;
  - ready-made chips use their topic's color;
  - weather filters read Dry, Light, Moderate, Heavy and Unknown, replacing "light, mod, Dry".
- **Landing page:**
  - the reliability topic names waits, missed trips, crowding and prediction accuracy;
  - the SQL sample matches the worst-routes question;
  - an FAQ explains the October 29 drop and the gap with RTD.

**After #116 and #117 merged** (hand-triggered nightly runs):
- **19:47 BigQuery ([run 42281558765](https://github.com/medsidd/whyline-denver/actions/runs/42281558765)):**
  - 85 models built, and 183 of 184 tests passed. The warning was the known monotonic-arrivals check (148 visits).
  - All seven new tests passed, including closure order on the rebuilt table.
  - The exporter removed 9 stale shards: route-day October 29 to November 5, and stop-hour November 5.
  - Nightly DuckDB then refreshed. The served copy has no duplicate route-days from October 29; earlier dates still hold 228 surplus rows until owner step 2.
- **20:04 BigQuery ([run 42284314298](https://github.com/medsidd/whyline-denver/actions/runs/42284314298)) failed on a transient BigQuery error, not on the change:**
  - The insert-overwrite script for `mart_reliability_by_route_day` finished its MERGE and dropped its temp table, then returned `backendError` ("Retrying may solve the problem").
  - dbt retried the whole script, which failed because the temp table was gone. The MERGE had committed, so the data was right, but the run stopped before tests and export.
  - The 20:13 re-run ([run 42285835717](https://github.com/medsidd/whyline-denver/actions/runs/42285835717)) built 85 of 85 models and passed 183 of 184 tests.
- **Descriptions in BigQuery:** 83 of the 85 tables and views have a table description and every column described. The two exceptions are `stg_rt_stop_visits` and `stg_rt_trip_status`, which the realtime image re-creates every 15 minutes. They pick it up when that image is next rebuilt.

**Owner steps after #116 merges:**

1. Deploy the new API image, which carries the equity question and the weather filter fallback: `whylinedenver-api@sha256:1f5db0b3b6c28cf851be88b5f738f7dc828ca42c5b57a3abced6c2ed688e6665`, Cloud Build `dbeceac8`, tag `2d90fa7`. The rollback is the R1 image above.

```bash
gcloud run services update whylinedenver-api --project=whyline-denver --region=us-central1 \
  --image=us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api@sha256:1f5db0b3b6c28cf851be88b5f738f7dc828ca42c5b57a3abced6c2ed688e6665
```

2. Clear the stale shards by re-exporting both reliability marts, then dispatch Nightly DuckDB:

```bash
cd ~/dev/whyline-denver && git pull && PYTHONPATH=$PWD/src GCP_PROJECT_ID=whyline-denver BQ_DATASET_MART=mart_denver GCS_BUCKET=whylinedenver-raw \
  .venv/bin/python -m whyline.sync.export_bq_marts --force --since 2025-10-23 \
  --mart mart_reliability_by_route_day --mart mart_reliability_by_stop_hour
```

### Owner steps checked, sidewalk condition added, RTD bus gap explained, November 7, 2026 (UTC)

**Owner steps after #116, both done:**
- **API deploy:** revision `whylinedenver-api-00015-cpk` serves `@sha256:1f5db0b3…`. The equity question now reads the mart's score; it returns 20 rows, led by 16th Street & Stout St (`22368`, priority 68.3).
- **Re-export:** the forced export between 14:05 and 14:26 UTC rewrote all 320 route-day folders, one shard each. Nightly DuckDB ([run 42385872329](https://github.com/medsidd/whyline-denver/actions/runs/42385872329)) then rebuilt the warehouse at 15:24.
- **Served copy, read from the uploaded warehouse:**
  - Route-day has 3,332 rows, one per route and date. Stop-hour has 1,209,174, one per stop, date and hour.
  - Through November 6, both match BigQuery exactly: 3,243 and 1,194,296 rows. November 7 differs only because BigQuery's current-day partition keeps growing.
  - The 228 surplus rows are gone.

**Found: a warm API instance keeps the warehouse it opened.**
- An instance that started at 15:18, before the upload, still returned the old duplicates through `engine: duckdb` at 15:25.
- Each worker thread opens one DuckDB connection and keeps it for the instance's life, so a refreshed warehouse reaches the API only on new instances. Minimum instances is 0, so idle instances are replaced, usually within the hour.
- A related risk: `_ensure_local_copy` copies a newer warehouse over `/tmp/warehouse.duckdb` in place, which other threads on the same instance may have open.
- Not changed that day. Fixed in code on November 7 (entry below); it reaches the API with the next image.

**Sidewalk condition (the empty fields found on November 6).**
- **Source:** Denver's sidewalk layer (`ODC_TRANS_SIDEWALKS_L/143`) has its status, surface and year-built fields, and eight others, empty on all 190,234 segments.
  - Its item description promises widths; the published fields carry none.
  - The city's **sidewalk asset inventory** (`ODC_ASSET_SIDEWALKS_L/416`, "Sidewalks Asset", public, updated August 2026) has them on 180,646 frontage segments, split by parcel: 171,311 with sidewalk and 9,335 marked "Missing Sidewalk" (344 miles).
  - It has width in whole feet on all but one segment: 71,854 are 4 ft and 92,040 are 5 ft. It also has the 2022 baseline condition (good 166,697, fair 3,934, poor 680) and surface on 95%.
  - No Denver layer publishes when a sidewalk was built.
- **Change:**
  - `arcgis_reference` fetches the asset layer weekly, with five fields only: 15.7 MB gzipped, in about 90 seconds.
  - `bridge_stop_street_safety` and `mart_stop_walk_safety` gain `frontage_m_100m` and three shares inside a 100 m circle: no sidewalk, under 5 ft (the width Denver's sidewalk plan treats as deficient), and fair or poor.
  - A new walk-safety flag marks stops with no sidewalk on a quarter or more of the frontage.
  - The empty `status`, `material` and `year_built` columns are dropped from `stg_sidewalks` and `dim_sidewalk_segment`; `raw_sidewalks` keeps its contract.
- **Checks before merge:**
  - BigQuery ran the new SQL on the real features near five stops. Lengths matched an independent planar calculation within 2%; BigQuery's buffer polygon is slightly smaller than a true circle.
  - Across the 2,707 Denver stops, 2,664 have inventoried frontage within 100 m.
  - The median stop has none of it missing. 311 stops have a quarter or more missing, and 98 have half or more; the worst are along 6th Avenue Parkway and Monaco Parkway.
  - 520 stops have at least half their sidewalk under 5 ft.
- **Loaded after merge ([#119](https://github.com/medsidd/whyline-denver/pull/119)):**
  - A hand-triggered Nightly Ingest ([run 42388055861](https://github.com/medsidd/whyline-denver/actions/runs/42388055861)) fetched the layer at 15:48 UTC and loaded 180,646 rows into `raw_arcgis_reference`.
  - The merged bridge SQL, run read-only against it, gives the same counts as the pre-merge check above (2,664, 311, 98, 520), and 633 stops with some fair or poor sidewalk.
  - The tables pick it up in the next Nightly BigQuery. `mart_stop_walk_safety` stays unpublished until release R2.

**RTD's bus gap, investigated.**
- **Season:** RTD's own all-bus figure stayed between 81.1% and 84.6% in all 20 months it reported, January 2025 to August 2026, including 82.0% and 82.9% in October and November 2025. Waiting for its October 2026 report won't close a 9-point gap.
- **Method:** the investigation counted bus visits on service dates October 30 to November 5, 2,021,091 visits with a known delay. RTD's published definition is only "less than one minute early or five minutes late". Each row below adds one rule, pooled over visits:

| Rule | Bus on time |
|---|---:|
| WhyLine as published: every stop, arrival (departure at the first stop), −60 < delay ≤ 300 s | 73.9% |
| Only GTFS timepoints (19% of visits) | 71.9% |
| Departure at timepoints: middle of the observed dwell where the vehicle was seen standing | 74.7% |
| "5 minutes late" read as under 6 minutes, as whole-minute schedules often count | 78.5% |
| Early arrival at a trip's last stop not counted against it | 81.2% |
| Latest departure the reports allow: the bus held at the timepoint until it left | 84.1% |
| RTD, August 2026 | 83.3% |

- **Other rules, each alone:** drop-off-only stops add 0.6 points, and leaving out the 16th Street FreeRide adds 0.6. Averaging routes equally instead of pooling visits adds 1.3–2.1 points at each step.
- **Timepoints:** at timepoints, 15.3% of arrivals are more than 5 minutes late and 12.7% more than a minute early. A bus can't leave before it arrives, so departure timing can shrink only the early share.
- **Conclusion:** the gap comes from counting rules, not missing or mismatched visits. With departures at timepoints, whole-minute lateness and no early penalty at the last stop, WhyLine reaches 81.2%, inside RTD's 20-month range. WhyLine keeps its stricter every-stop rule; the glossary, the landing FAQ and the dashboard note now say this.
- **To settle it:** RTD was asked how it treats departures, whole minutes, the last timepoint and missing AVL data. The question went in records request RTD-2026-1065, submitted on November 7 with the WP11 boardings and stop-amenity request ([request text](plans/rtd-records-request.md)). Under CORA, RTD should respond within three working days, or ten if it claims an extension; research beyond the first hour costs $30 an hour, and the request asks for an estimate first.

### DuckDB reopens a refreshed warehouse, November 7, 2026 (UTC)

**Code change, not yet deployed.** `src/whyline/engines/duckdb_engine.py` fixes the warm-instance issue found earlier today.
- **Copies:** each warehouse version is copied to its own file named after the source's modification time and size, `/tmp/warehouse-<mtime_ns>-<size>.duckdb`. The copy is written under a `.tmp` name and renamed into place, and older copies are deleted. A thread still reading an old copy keeps its open file. A failed copy leaves no `.tmp` behind, and the current copy keeps serving.
- **Reopening:** one shared check reads the source at most once a minute; other threads keep the current copy while it copies. Each thread opens the new copy on its next query, and keeps its old connection if the new one fails to open.
- **Lag:** results can trail a refresh by the one-minute check, the GCS mount's metadata cache, and the API's 180-second query cache for repeated SQL.
- **Local:** with `DUCKDB_COPY_LOCAL=0` (the local default) connections still keep the warehouse they opened; restart the API after `make sync-duckdb`.
- **Why a new name:** DuckDB returns the database it already has open for a path, so reopening `/tmp/warehouse.duckdb` would have kept the old data.
- **Tests:** `tests/engines/test_duckdb_engine.py` covers the reopen, a failed reopen, a failed copy and an unreadable source. A stress run with 16 threads querying while the source was replaced six times saw every version, no errors and one copy left.
- **Still the same:** the stop and route lookups in `api/deps.py` are cached for the life of the process.
- **To deploy:** build a new API image, then the owner runs `gcloud run services update`. Check it by running a new `engine: duckdb` query (not one run in the last three minutes) on a warm instance a few minutes after Nightly DuckDB.

### Dashboard QA and PR 1 checks, November 7, 2026 (UTC)

**End-to-end QA of production.** Run in Playwright against whylinedenver.com, it used about 15 BigQuery queries (each well under 50 MB), 1 Gemini call and 2 downloads. Findings and the owner's decisions are in the [dashboard QA plan](plans/dashboard-qa-fixes.md).

**PR 1 checks before merge** (local API on BigQuery with the stub LLM, local frontend):
- BigQuery dry runs of all 8 ready-made questions, with no filters and with dates, routes, stop and weather set: all valid, the largest 42.7 MB (slow segments).
- 16 runs of the questions (rail dates, then route 15 added) returned rows, plus a handful of dashboard runs and two 1,000-row downloads, all under 50 MB each.
- A route value with a quote, a non-date `date_start` and an unlisted `date_column` were rejected.

**After merge ([#124](https://github.com/medsidd/whyline-denver/pull/124)):**
- **Production frontend** (deployment of `8ef4464`), checked in headless Chrome at 1280 and 390 px against the old API: the equity question charts priority score by stop name, the scan estimate shows on load, "zzz" gets the no-route message, a row limit of −5 is blocked, no console errors and no sideways scroll. The new explanations, filter notes and guardrail message need the new API.
- **API image built, not deployed:** Cloud Build `962bb4f7` at 23:17 UTC, tag `8ef4464`, `whylinedenver-api@sha256:a35af41f53285e15d86512f0eeeb982cd24a8d6fcd420bf176447e9c4bf53e10`. It carries PR 1 and the DuckDB reopen from [#123](https://github.com/medsidd/whyline-denver/pull/123).

**Owner step:** deploy it. The rollback is the current `@sha256:1f5db0b3…` (#116).

```bash
gcloud run services update whylinedenver-api --project=whyline-denver --region=us-central1 \
  --image=us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api@sha256:a35af41f53285e15d86512f0eeeb982cd24a8d6fcd420bf176447e9c4bf53e10
```

### PR 1 verified on production, PR 2 checks, November 8, 2026 (UTC)

**PR 1 after the owner's API deploy.** Revision `whylinedenver-api-00016-m4b` serves `@sha256:a35af41f…`.
- `curl`: question 0 with route 15 and stop 12084 applied dates and routes and skipped the stop; a route value with a quote was dropped and reported; "SELEC" got the new message; an unlisted `date_column` returned 400; the second `/api/filters/bigquery` call took 0.15 s (9.1 s cold).
- Headless Chrome on whylinedenver.com, route 15 and stop 12084 set: all 8 questions loaded with the expected filter note and an estimate before any edit, ran in 2.8–4.7 s, and charted (frequency has no chart by design). No console errors. About 10 BigQuery queries, each under 50 MB; no Gemini calls.
- The DuckDB reopen from #123 is in this image; it is checked after the next Nightly DuckDB.

**PR 2 before merge** (local API on BigQuery with the stub LLM, production build of the frontend):
- The equity chip opened `/app?prebuilt=3`, loaded the question and called neither generation nor run.
- The map fit its 20 points; full screen covered the page at 390 px and locked scroll; Escape restored it.
- Table headers sorted ascending, descending and back; "Stop name" sat next to "Stop ID".
- A trend ending today showed the note; autocomplete offered `mart_gtfs_routes` with no icons.
- The whole-table download of route-day reliability with the rail's dates returned 935 rows, newest first.
- About 12 BigQuery queries, each under 50 MB.

### PR 2 on production, PR 3 checks and owner steps, November 8, 2026 (UTC)

**PR 2 after merge ([#126](https://github.com/medsidd/whyline-denver/pull/126)).** Headless Chrome on whylinedenver.com, with the PR 1 API still serving: the equity chip loaded its question without generation or run calls; header "Nov 7, 5:36 PM MST"; skeleton, CSV name, map fit and key, full screen at 390 px with scroll locked, table sort, today note, autocomplete and the dated whole-table download (935 rows) all worked, with no console errors. One Gemini call (the waiting-line check) and about 12 BigQuery queries, each under 50 MB.

**API image for PR 2, built, not deployed:** Cloud Build `7912c4a4`, tag `8e88f87`, `whylinedenver-api@sha256:04c8dd11af6ecada36f93ac8fb2428b2d60c4f10cae90f197d2edf53b846eb14`. It adds newest-first whole-table downloads and the prompt's exact date predicate. Rollback: `@sha256:a35af41f…` (PR 1).

```bash
gcloud run services update whylinedenver-api --project=whyline-denver --region=us-central1 \
  --image=us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api@sha256:04c8dd11af6ecada36f93ac8fb2428b2d60c4f10cae90f197d2edf53b846eb14
```

**PR 3 before merge** (production build, local API): `robots.txt`, `sitemap.xml` and the canonical and `og:url` tags of all five pages were correct; an unknown path returned the branded 404 with status 404; axe found 0 violations on every page at 1280 and 390 px; the skip link moved focus to `main`; a mocked 429 showed the friendly message on run and download.

**PR 3 after merge ([#127](https://github.com/medsidd/whyline-denver/pull/127)).** On whylinedenver.com: `robots.txt` and the five-page `sitemap.xml` are served, `/` and `/app` carry their canonical and `og:url`, an unknown path returns the branded 404 with status 404, and axe reports 0 violations on every page at 1280 and 390 px. A regression run of all 8 ready-made questions (route 15, stop 12084) and the phone flow passed with no console errors; about 10 BigQuery queries, each under 50 MB. One Vercel preview build failed with no code change and passed on a rebuild.

**PR 2's API deployed by the owner** at 03:17 UTC on November 8: revision `whylinedenver-api-00017-bxk` serves `@sha256:04c8dd11…`. Checked on production right after:
- An undated whole-table download of route-day reliability returned 1,000 rows from November 7 back to October 30, newest first (the previous revision returned February 2026 to November 2025 in no order). A dated download of wait-by-route stayed within its dates, newest first.
- One Gemini question with dates November 1–6 came back with a single date predicate, exactly the user's range.
- The DuckDB reopen from #123 still needs its check: dispatching Nightly DuckDB from the agent session was refused by the permission check, so it waits for the scheduled 09:30 UTC run. Check: run an `engine: duckdb` query before 09:30 to warm an instance, then a different one a few minutes after the upload, and look for a `Copying DuckDB from` log line after the upload time.

**Owner step: rate limits (owner decision of November 7, 2026).** Install and link the Vercel CLI (`npm i -g vercel`, then `cd frontend && vercel link`). Stage both rules in log mode, review, then publish:

```bash
vercel firewall rules add "Rate limit SQL and queries" \
  --condition '{"type":"path","op":"inc","value":["/api/sql/generate","/api/query/run"]}' \
  --condition '{"type":"method","op":"eq","value":"POST"}' \
  --action rate_limit --rate-limit-window 60 --rate-limit-requests 20 --rate-limit-keys ip \
  --rate-limit-action log --yes
vercel firewall rules add "Rate limit downloads" \
  --condition '{"type":"path","op":"pre","value":"/api/downloads/"}' \
  --action rate_limit --rate-limit-window 60 --rate-limit-requests 5 --rate-limit-keys ip \
  --rate-limit-action log --yes
vercel firewall diff
vercel firewall publish --yes
```

After a few days of the firewall traffic view showing only heavy clients, remove each rule and add it again with `--rate-limit-action rate_limit` (a 429), then publish. Check by sending 21 quick `POST /api/query/run` requests: the 21st should get 429. Counters are per Vercel region, so a client spread across regions can exceed the limit. The rule only covers traffic through whylinedenver.com: the Cloud Run origin stays reachable directly, and restricting its ingress is a separate decision.

**Owner step: apex redirect.** `https://whylinedenver.com/` answers 307 to `www`. In Vercel → Project → Settings → Domains, set the apex redirect to permanent (308).

### Realtime stream outage, November 7–9, 2026 (UTC)

**Found November 9 at 10:50 UTC.** `raw_gtfsrt_vp_stream`, `raw_gtfsrt_stop_visits` and `raw_gtfsrt_trip_status` received no rows after 14:47 UTC on November 7. `realtime-load` kept succeeding on empty files, and the heartbeat kept beating, so nothing alerted. `fct_stop_visit`, `fct_trip_status` and every mart built on them have no data from then until the fixed poller runs.

**Cause.** At 14:47:42 the poller loaded a new static GTFS version (`641ea889…`, feed of November 5) and the next payload failed in the visit engine with `IndexError: array index out of range`; every trip-update and vehicle-position payload failed after that.
- `StaticCache.add` evicted a superseded version once it was 36 hours past its *load* time. The previous version (`b640c864…`) had been loaded on October 30, so it was dropped the moment the new one arrived, while trips that started on it were still open.
- Their lookups fell back to the new version, whose stop lists differ, and a visit's stop index ran past the end.
- `_sweep` raised before the trip could close, so the same trip failed every payload. Open trips grew to about 5,350 and the container restarted every 15 minutes from a checkpoint holding the same trips, so restarts didn't help.

**Data lost.** Payloads were archived only after the engine processed them, so the archive tars from 15:00 on November 7 are empty (2 KB) and the outage cannot be replayed. The snapshot ingest (`realtime-ingest`) is paused, so there is no second copy. Stop visits, trip status and vehicle reports from 14:47 UTC on November 7 until the fixed poller runs are gone. Marts will show no realtime data for those dates.

**Fix ([#130](https://github.com/medsidd/whyline-denver/pull/130)).**
- A trip is never read against a version other than the one it started on: if that version is gone, it is treated as having no static and closes as `no_static`.
- A superseded version is kept 36 hours from when it was superseded, and a restart reloads the versions open trips are pinned to.
- An error in one trip closes that trip (counted as `trip_errors` in the heartbeat) instead of failing the payload.
- A payload that parses but fails in the engine is still archived, so a future engine bug can be replayed.
- Checks: regression tests that fail without the fix, the full suite, and a replay of the archived November 7 payloads (00:00–14:45) through the fixed engine with no errors.

### Query usage report

From release R1 of the [metrics plan](plans/metrics-implementation.md), the first API image with WP0's change, every query run on Cloud Run also logs one JSON line, `jsonPayload.event="query"`. It records the marts used, the ready-made question number if one was run unedited, row count, status and latency. Question and SQL text are hashed. A weekly read-only summary:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.event="query"' --project=whyline-denver \
  --freshness=7d --format='value(jsonPayload.model_names,jsonPayload.prebuilt_index,jsonPayload.status)' | sort | uniq -c | sort -rn | head -30
```

Vercel also receives `question_run` and `download` events. Custom events only show on Vercel plans that include them.

## Refresh state read-only

```bash
curl -fsS --max-time 30 https://www.whylinedenver.com/api/health
curl -fsS --max-time 30 https://www.whylinedenver.com/api/freshness
gh workflow list --repo medsidd/whyline-denver --all
gh run list --repo medsidd/whyline-denver --limit 10
gcloud scheduler jobs list --project=whyline-denver --location=us-central1   --format='table(name.basename(),state,schedule)'
gcloud run jobs executions list --project=whyline-denver --region=us-central1   --job=realtime-load --limit=5
```

Inspect `realtime-ingest` separately. Read image digests in job/execution descriptions when validating a deployment; avoid dumping environment/secret values into reports. gcloud may need to write its local credential database even for a read-only API request; a sandbox write error is not evidence the cloud resource is down.

## Refresh billing

The billing export is ingestion-time partitioned. Use bounded queries and account for credits without multiplying costs by an unnested credit join. This example scans recent export partitions and reports current-month usage by service:

```sql
SELECT
  service.description AS service,
  currency,
  SUM(cost) AS gross,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credits,
  SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net,
  MAX(usage_end_time) AS latest_usage,
  MAX(export_time) AS latest_export
FROM `whyline-denver.billing.gcp_billing_export_v1_010059_B03714_C2A403`
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(
    TIMESTAMP(DATE_TRUNC(CURRENT_DATE('America/Los_Angeles'), MONTH), 'America/Los_Angeles'),
    INTERVAL 2 DAY)
  AND project.id = 'whyline-denver'
  AND DATE(usage_start_time, 'America/Los_Angeles') >=
      DATE_TRUNC(CURRENT_DATE('America/Los_Angeles'), MONTH)
  AND DATE(usage_start_time, 'America/Los_Angeles') <= CURRENT_DATE('America/Los_Angeles')
GROUP BY service, currency
ORDER BY net DESC;
```

Run via `bq query --project_id=whyline-denver --location=us-central1 --use_legacy_sql=false --maximum_bytes_billed=200000000`, supplying the SQL through a file/stdin. The query itself can be billable; inspect a dry run first if the scan approaches the cap. To analyze the trend, group by local usage date and SKU. To diagnose compute, inspect region-appropriate BigQuery job metadata; that gives workload attribution, not final net billing.

## Source endpoint maintenance

October 26 read-only requests confirmed both legacy RTD realtime URLs redirect to working canonical protobuf endpoints. [RTD documents the new feed addresses and legacy deprecation](https://www.rtd-denver.com/open-records/open-spatial-information/real-time-feeds). The realtime ingestors now default to the canonical endpoints; a deployed image built before that change still requests the legacy addresses. Static GTFS still uses the redirecting legacy address. See [realtime strategy](../guides/GTFS_RT_Strategy.md) for the exact targets.

## Changes to operations

Pausing/resuming, redeploying, dispatching batch jobs, and changing identities require a scoped operational task. Review current state and retain image/revision rollback references first. For recovery, run ingest → transformations/tests/export → DuckDB sequentially and verify each completion before starting the next. Use [deployment](DEPLOYMENT.md) and [pipeline](DATA_PIPELINE.md); do not paste obsolete scheduler-creation examples into a running project.
