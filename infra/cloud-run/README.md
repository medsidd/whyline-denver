# Realtime Cloud Run jobs

The shared [Dockerfile](Dockerfile) packages Python dependencies, application source, dbt, Makefile, and launcher tools. [entrypoint.sh](entrypoint.sh) selects one of two behaviors using `JOB_TYPE`:

| Job | Required mode | Work performed |
|---|---|---|
| `realtime-ingest` | `ingest` (default) | Fetch RTD Trip Updates and Vehicle Positions, serialize CSV/gzip, upload raw snapshot and manifest |
| `realtime-load` | `load` | `make bq-load-realtime`, `make dbt-run-realtime`, then `make update-bq-timestamp` |
| Stream poller VM (not a Run job) | `stream` | `whyline.ingest.gtfs_rt_stream`: polls both feeds every 15 s, uploads one batch per table and an archive tar every 15 minutes; needs `GCS_BUCKET` and `ARCHIVE_BUCKET`, state in `STATE_DIR` (`/state`). Installed by [`infra/stream-vm/cloud-init.yaml`](../stream-vm/cloud-init.yaml); see the [plan runbook](../../docs/technical/plans/realtime-stop-visits.md#7-runbook-owner-commands-in-order). |

Ingest requires `GCS_BUCKET`; `GTFS_SNAPSHOTS` defaults to 1 and `GTFS_INTERVAL_SEC` to 120 (only separates snapshots when there is more than one). `GTFS_EXTRA_FLAGS` is split into additional CLI arguments. Do not put secrets in extra flags; the entrypoint uses shell tracing.

Load uses BigQuery/GCS project/dataset settings and dbt credentials. Despite its name, the loader scans all registered source patterns in its date window. The realtime dbt selection is a subset (`stg_rt_events`, `fct_trip_observation`, `fct_stop_arrival`, two reliability marts) and requires the dimensions and schedule fact built nightly. Neither branch performs the nightly Parquet export/DuckDB refresh.

## Scheduling and deployment

Cloud Scheduler is the recurring trigger. Verified October 26, 2026: ingest `*/15 * * * *`; load `2-59/15 * * * *`; both enabled. The two realtime GitHub workflow definitions are manual alternatives. Do not restore older five-minute schedules from historical examples.

Build from reviewed source including `tools/dbt_with_env.py`, and deploy the same immutable image digest to both jobs when shared source changes. An existing Run job does not automatically update when `:latest` is pushed. Preserve current job configuration and inspect real executions after updating. Detailed commands and credential boundaries are in [deployment](../../docs/technical/DEPLOYMENT.md).

## Read-only inspection

```bash
gcloud scheduler jobs list --project=whyline-denver --location=us-central1   --format='table(name.basename(),state,schedule)'
gcloud run jobs executions list --project=whyline-denver --region=us-central1   --job=realtime-load --limit=5
```

Inspect ingest executions separately and confirm actual raw/mart timestamps; enabled schedules and successful job configuration updates are not proof of data delivery. [Operations](../../docs/technical/OPERATIONS.md) records dated state/costs and [realtime strategy](../../docs/guides/GTFS_RT_Strategy.md) explains sampling limits.
