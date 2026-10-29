# Operational QA validation

Use this checklist to distinguish configured, enabled, executing, completed, fresh, and correct. A health endpoint or aggregate success percentage cannot substitute for the individual checks. See [operations](technical/OPERATIONS.md) for the dated baseline and [testing](technical/TESTING.md) for offline code checks.

## Start with read-only evidence

1. Inspect repository changes and the intended deployed source revision.
2. Read recent nightly workflow conclusions and both realtime job executions.
3. Read actual scheduler state/cadence. An enabled job can still fail every run.
4. Compare source, staging, mart, export, warehouse, and served-result dates.
5. Validate completeness/missingness and a representative result, not only timestamps.

```bash
gh run list --repo medsidd/whyline-denver --limit 10
gcloud scheduler jobs list --project=whyline-denver --location=us-central1   --format='table(name.basename(),state,schedule)'
gcloud run jobs executions list --project=whyline-denver --region=us-central1   --job=realtime-ingest --limit=5
gcloud run jobs executions list --project=whyline-denver --region=us-central1   --job=realtime-load --limit=5
curl -fsS --max-time 30 https://www.whylinedenver.com/api/health
curl -fsS --max-time 30 https://www.whylinedenver.com/api/freshness
```

The recurring schedulers were observed at 15-minute intervals, giving 96 nominal invocations per full day per job. Partial days, failures, scheduler delay, source emptiness, and duplicate feed timestamps can reduce observed snapshot counts. Do not assume fixed row volumes or diagnose duplicate rows from a large timestamp group: many legitimate stop/trip rows share a feed timestamp.

## Raw and model checks

BigQuery checks are read-only data queries but can incur analysis charges. Use bounded dates, correct physical partition columns, dry runs, and a maximum-bytes-billed cap. Examples:

```sql
SELECT MAX(feed_ts_utc) AS newest_snapshot,
       COUNT(DISTINCT feed_ts_utc) AS snapshots,
       COUNT(*) AS source_rows
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY);
```

```sql
SELECT station, MIN(date) AS first_date, MAX(date) AS last_date,
       COUNT(*) AS days, COUNTIF(precip_mm IS NULL) AS missing_precip_days
FROM `whyline-denver.stg_denver.stg_weather`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY)
GROUP BY station;
```

```sql
SELECT service_date_mst, COUNT(*) AS route_day_rows,
       COUNTIF(route_id IS NULL) AS null_routes,
       COUNTIF(precip_bin = 'unknown') AS unknown_weather_rows,
       SUM(n_events) AS events,
       SUM(n_reported_events) AS reported_delay_events
FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`
WHERE service_date_mst >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 7 DAY)
GROUP BY service_date_mst ORDER BY service_date_mst;
```

Check zero null routes and on-time values within 0–1; inspect event/reporting coverage before trusting the rate. Missing transit delay can be coalesced to zero, while missing weather must remain unknown/null. Weather-impact rows require observed weather; dry baselines can be null if no dry-day overlap exists. A daily window need not have a fixed completeness percentage.

### Stream and stop visits

Once the stream poller is deployed, check that batches keep arriving and how visits were timed. Raw stop visits are partitioned by load hour, so this reads one day:

```sql
SELECT TIMESTAMP_TRUNC(_ingested_at, HOUR) AS load_hour,
       COUNT(DISTINCT _source_path) AS batches,
       COUNT(*) AS visits,
       COUNTIF(arrival_method = 'shape_crossing') / COUNT(*) AS share_crossing_30s,
       COUNTIF(arrival_method = 'last_prediction') / COUNT(*) AS share_last_prediction
FROM `whyline-denver.raw_denver.raw_gtfsrt_stop_visits`
WHERE _ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
GROUP BY load_hour ORDER BY load_hour;
```

Expect four batches an hour. Then compare yesterday's visits with the schedule by route:

```sql
WITH s AS (
  SELECT route_id, COUNT(*) AS scheduled
  FROM `whyline-denver.core_denver.fct_scheduled_stop_time`
  WHERE service_date_mst = DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
  GROUP BY route_id),
v AS (
  SELECT route_id, COUNTIF(NOT skipped) AS visits, COUNTIF(within_30s) AS within_30s
  FROM `whyline-denver.core_denver.fct_stop_visit`
  WHERE service_date = DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
  GROUP BY route_id)
SELECT s.route_id, s.scheduled, v.visits,
       SAFE_DIVIDE(v.visits, s.scheduled) AS share_observed,
       SAFE_DIVIDE(v.within_30s, v.visits) AS share_within_30s
FROM s LEFT JOIN v USING (route_id)
ORDER BY share_observed;
```

Canceled trips and vehicles that never reported lower `share_observed`; rail windows are wider than bus windows by design. `assert_stream_visits_reach_fact` fails if raw visits from two to three days ago are missing from the fact. The [dual-run checklist](technical/plans/realtime-stop-visits.md#6-dual-run-and-cutover-checklist-owner) lists the checks to pass before the marts switch to stop visits.

Authorized `make dbt-test-staging` / `make dbt-test-marts` run data assertions. Separate missing data from model execution failures; do not silently repair by deleting raw records or treating null weather as dry.

## Export and warehouse checks

- Confirm the BigQuery export completed and the expected `marts/{name}/run_date=…/` objects changed. A job timestamp can advance while an older partition remains stale.
- For a late weather correction, check the older partition's `build_run_at` and export selection as well as the latest service date.
- Confirm DuckDB refresh uploaded the intended file and updated sync state.
- Query the actual DuckDB file to check the nine expected tables, date ranges, and the same bounded aggregate used in BigQuery. Compare matching cutoffs; realtime BigQuery can be newer than the nightly warehouse.
- Requery through the public DuckDB API. Existing connections, result caches, lookups, or stale schema artifacts can disagree with the newest GCS object.

For a local downloaded warehouse, this inspection does not contact BigQuery:

```bash
.venv/bin/python - <<'PYTHON'
import duckdb
con = duckdb.connect('data/warehouse.duckdb', read_only=True)
print(con.execute('SHOW TABLES').fetchall())
print(con.execute('SELECT MIN(service_date_mst), MAX(service_date_mst), COUNT(*) FROM mart_reliability_by_route_day').fetchall())
con.close()
PYTHON
```

## Browser and API checks

Open `/app`, load a prebuilt query, review/validate/run it, and inspect table/chart/map. Check a known stop name/coordinate, route enrichment, result CSV, mart CSV, warehouse download, and freshness labels. Verify `/api/models` lists the expected nine marts; `/api/health` does not test those artifacts.

For generated SQL, use stub locally or an authorized provider configuration. The weather prebuilt label refers to snow, but its current SQL tests moderate/heavy precipitation; do not report snow-specific results from it.

## Legacy QA helper

`tools/qa_script.sh` is a legacy convenience script, not the authority for current platform health. Inspect its SQL, assumptions, side effects, and availability before running it. The old guide's fixed row targets, Streamlit checks, automatic repair suggestions, and numerical health grades were removed because they could mask failures or recommend unnecessary writes.

Record dated conclusions separately for code tests, job completion, source coverage, data correctness, served results, and billing. State any layer not verified.
