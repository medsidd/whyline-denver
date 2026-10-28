# GitHub Actions workflows

Six workflow definitions live directly in this directory. The three nightly workflows are independently scheduled; the two realtime workflows are manual alternatives to Cloud Scheduler/Run. This reference describes checked-in YAML/Makefile behavior, not a guarantee that a workflow is enabled or completed. See [operations](../../docs/technical/OPERATIONS.md) for dated live readback.

## Triggers and work

| Workflow | Trigger | Work performed |
|---|---|---|
| [ci.yml](ci.yml) | Pull requests; pushes to `main` | Python install, Ruff/Black lint, offline pytest and ingestion-selected tests. On successful main pushes, separate jobs generate dbt docs with cloud credentials and deploy Pages. |
| [nightly-ingest.yml](nightly-ingest.yml) | `0 8 * * *` UTC; manual | `make nightly-ingest-bq`: static-source extraction plus date-window BigQuery loading. Static recipe includes GTFS, crashes, sidewalks, rolling NOAA, configured ACS, and a nonfatal tract attempt. |
| [nightly-bq.yml](nightly-bq.yml) | `0 9 * * *` UTC; manual | `make nightly-bq`: dbt selection `'staging core marts'`, core and mart tests, then Parquet export. Workflow updates BigQuery timestamp and uploads existing artifact files. |
| [nightly-duckdb.yml](nightly-duckdb.yml) | `30 9 * * *` UTC; manual | `make nightly-duckdb`: refresh/materialize all nine marts into DuckDB, upload configured warehouse/state; attach local files as workflow artifacts. |
| [realtime-gtfs-rt.yml](realtime-gtfs-rt.yml) | Manual only | Capture one GTFS-RT snapshot to GCS. No recurring GitHub cron. |
| [realtime-bq-load.yml](realtime-bq-load.yml) | Manual only | Date-window raw loading, realtime dbt subset, and BigQuery timestamp update. No recurring GitHub cron. |

Cron expressions are UTC and requested starts can be delayed. There is no `workflow_run`/completion chain between the nightly jobs. A 30-minute offset does not ensure the preceding export finished. For recovery, dispatch and verify stages sequentially: ingestion → transformation/tests/export → DuckDB.

Nightly runs rebuild the dimensions and refresh the schedule fact (today through +30 days); incremental facts and marts only process their recent windows, so history changes need a deliberate `--full-refresh`. Uploading a file as an artifact does not prove it was regenerated in that run: inspect producing steps and timestamps. See [pipeline](../../docs/technical/DATA_PIPELINE.md).

## Recurring realtime work

Cloud Scheduler invokes Cloud Run jobs `realtime-ingest` and `realtime-load`; October 26, 2026 readback showed 15-minute capture and offset load schedules, both enabled. Do not diagnose those schedules from missing manual GitHub realtime runs. The shared image, job identities, and deployment instructions are in [infra/cloud-run](../../infra/cloud-run/README.md).

## Credentials and configuration

The YAML maps service-account credentials into a temporary workspace credential file and passes project/dataset/bucket values to consuming steps. Inspect secret names and bindings without printing their values. Existing secret names include `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_RAW`, `BQ_DATASET_STG`, `BQ_DATASET_MART`, `NOAA_CDO_TOKEN`, and `CENSUS_API_KEY`.

Census must be mapped into the ingestion process; merely storing the secret does not do that. The October recovery fixed exactly that boundary. Provider keys for the API are configured separately in Cloud Run, not by these batch secrets.

The offline CI build job needs no BigQuery credentials. The docs jobs use them for `pages-build`; do not describe the full CI workflow as entirely offline. `make test` no longer generates production dbt artifacts.

## Inspect and recover

```bash
gh workflow list --repo medsidd/whyline-denver --all
gh run list --repo medsidd/whyline-denver --workflow nightly-ingest.yml --limit 5
gh run list --repo medsidd/whyline-denver --workflow nightly-bq.yml --limit 5
gh run list --repo medsidd/whyline-denver --workflow nightly-duckdb.yml --limit 5
```

Inspect a specific run's jobs/logs and data outputs when it fails. Distinguish queued, running, failed, cancelled, skipped, and succeeded. A failed test prevents later steps in that recipe; it does not pause independently scheduled jobs. GitHub notification/branch-protection settings are external to this YAML and must be verified separately before promising alerts or merge blocking.

Workflow dispatches, secret changes, schedule changes, and deployments are operational writes; keep them within the authorized task. A docs cleanup does not authorize replaying paid batch jobs. [QA validation](../../docs/QA_Validation_Guide.md) covers actual content/freshness checks.

## Costs and maintenance

There is no maintained fixed annual workflow/platform cost or guaranteed free allowance here. GitHub runner billing and Google Cloud processing are separate. Use the [billing snapshot and refresh query](../../docs/technical/OPERATIONS.md) for project Google Cloud costs and inspect GitHub billing independently if needed.

Update this table when changing workflow triggers, selections, artifacts, or secret mappings. Shared source fixes must also reach the Cloud Run image used by realtime jobs; changing a checkout-based GitHub workflow does not redeploy that image.
