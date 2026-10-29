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

Physical storage billing (decision 6) is deferred until after a week of real pipeline runs, so it can be judged on billed costs.

`whylinedenver-raw` keeps every overwritten or lifecycle-deleted object as a noncurrent version, with no rule that removes them (for example, 151 versions of the DuckDB warehouse). That is unmeasured storage cost worth reviewing alongside the billing decision.

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
