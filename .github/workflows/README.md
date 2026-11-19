# GitHub Actions workflows

Five workflow definitions live in this directory. The nightly pair is a chain: Nightly BigQuery starts when Nightly Ingest finishes. Recurring realtime work runs on Cloud Scheduler and Cloud Run, not here. This reference describes the checked-in YAML and Makefile; see [operations](../../docs/technical/OPERATIONS.md) for dated live readback.

## Triggers and work

| Workflow | Trigger | Work performed |
|---|---|---|
| [ci.yml](ci.yml) | Pull requests; pushes to `main` | Python install, Ruff/Black lint, offline pytest, and the frontend lint, unit specs and build. On successful main pushes, separate jobs generate dbt docs with cloud credentials and deploy Pages. |
| [nightly-ingest.yml](nightly-ingest.yml) | `17 8 * * *` UTC; manual | `make nightly-ingest-bq`: static-source extraction plus date-window BigQuery loading, then `make dbt-source-freshness`. |
| [nightly-bq.yml](nightly-bq.yml) | When Nightly Ingest completes; manual | `make nightly-bq`: `dbt build` of `staging core marts` (models and their tests), then `make update-bq-timestamp` for the dashboard's "Data updated" time. Uploads dbt artifacts. |
| [realtime-bq-load.yml](realtime-bq-load.yml) | Manual only | Date-window raw loading, the realtime dbt subset and the timestamp update, the same work as the `realtime-load` Cloud Run job. |
| [weekly-access.yml](weekly-access.yml) | `23 6 * * 1` UTC; manual | Job-access travel times (r5py), then load. |

Cron expressions are UTC and GitHub can start them hours late (off-the-hour minutes are delayed least). Nightly BigQuery runs whatever Nightly Ingest's result, so a failed source download doesn't stop the build. The app reads BigQuery directly; nothing is exported after the build (the Parquet export and DuckDB copy were removed on November 19, 2026).

Nightly runs rebuild the dimensions and refresh the schedule fact (today through +30 days); incremental facts and marts only process their recent windows, so history changes need a deliberate `--full-refresh`. See [pipeline](../../docs/technical/DATA_PIPELINE.md).

## Recurring realtime work

Cloud Scheduler runs the Cloud Run job `realtime-load` every 15 minutes (`2-59/15`), and the VM `whyline-rt` runs the continuous GTFS-RT poller. The shared image, identities and deployment are in [infra/cloud-run](../../infra/cloud-run/README.md).

## Credentials and configuration

The YAML writes the service-account credentials to a temporary workspace file and passes project, dataset and bucket values to the steps that use them. Inspect secret names and bindings without printing their values. Secret names include `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_RAW`, `BQ_DATASET_STG`, `BQ_DATASET_MART`, `NOAA_CDO_TOKEN` and `CENSUS_API_KEY`. API provider keys are configured in Cloud Run, not here.

The CI build job needs no BigQuery credentials; the docs jobs use them for `pages-build`.

## Inspect and recover

```bash
gh workflow list --repo medsidd/whyline-denver --all
gh run list --repo medsidd/whyline-denver --workflow nightly-ingest.yml --limit 5
gh run list --repo medsidd/whyline-denver --workflow nightly-bq.yml --limit 5
```

Inspect a failed run's jobs, logs and data outputs. Distinguish queued, running, failed, cancelled, skipped and succeeded. Workflow dispatches, secret changes, schedule changes and deployments are operational writes; keep them within the authorized task. [QA validation](../../docs/QA_Validation_Guide.md) covers content and freshness checks.

## Maintenance

GitHub runner billing and Google Cloud processing are separate; see the billing query in [operations](../../docs/technical/OPERATIONS.md). Update this table when changing workflow triggers, selections, artifacts or secret mappings. Shared source fixes must also reach the Cloud Run image the realtime job and VM use; a checkout-based workflow change does not redeploy it.
