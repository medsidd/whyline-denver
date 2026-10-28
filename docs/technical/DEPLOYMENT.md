# Deployment

This is a deployment reference, not an instruction to start or redeploy resources during setup. Preserve retained data and inspect current state first. [Operations](OPERATIONS.md) contains the dated live snapshot; source configuration is not evidence of a completed deployment.

## Deployed components

| Component | Configuration/source |
|---|---|
| FastAPI Cloud Run service `whylinedenver-api` | `api/Dockerfile`, `infra/api-service/cloudbuild.yaml`, Makefile `api-build` / `api-deploy` |
| Cloud Run jobs `realtime-ingest`, `realtime-load` | Shared `infra/cloud-run/Dockerfile` and `entrypoint.sh`; `JOB_TYPE` selects behavior |
| Cloud Scheduler | Calls the Run jobs API with an authorized identity; inspect actual schedules |
| Next.js on Vercel | `frontend/` build, server-side `API_BASE_URL` |
| Nightly workflows and CI | `.github/workflows/*.yml`; cron jobs are independent |
| Model documentation | CI generates dbt artifacts and publishes GitHub Pages on successful pushes to `main` |

Project: `whyline-denver`; region: `us-central1`; bucket: `whylinedenver-raw`. Cloudflare/domain/Vercel configuration is external to this repository; verify those settings before claiming automatic deployment behavior.

## API service

After reviewing the intended source and environment, an authorized API deployment uses:

```bash
GEMINI_API_KEY_SECRET=gemini-api-key:latest make api-deploy
```

This submits a Cloud Build, pushes `us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api:latest`, and deploys the service. Makefile defaults: 0–3 instances, concurrency 80, 2 CPUs, 2 GiB memory, gen2 execution environment, unauthenticated access, service identity `api-service@whyline-denver.iam.gserviceaccount.com`.

It sets DuckDB as engine, Gemini as provider, the API query byte cap, and dataset/state locations. It mounts the bucket at `/mnt/gcs`, sets `DUCKDB_PATH=/mnt/gcs/marts/duckdb/warehouse.duckdb` and `DUCKDB_COPY_LOCAL=1`, and maps the Gemini secret. Prefer Secret Manager references over literal keys. Required capabilities include BigQuery read/job creation, GCS read, and access to the specific Gemini secret; grant the narrow scope required by the deployment.

Check usable manifest/catalog artifacts are included. `api/Dockerfile` consumes local artifacts; CI's generated artifacts do not automatically update a separately built API image. A healthy service without current artifacts may still fail `/api/models` or SQL generation.

## Realtime shared image

See [container reference](../../infra/cloud-run/README.md). Build from a clean reviewed source export containing `src/`, `dbt/`, `tools/`, `Makefile`, requirements, and `infra/cloud-run/`. Inspect included tracked files before uploading; exclude credentials, local raw data, generated artifacts, and unrelated work.

The Makefile offers `cloud-run-build` (local Docker), `cloud-run-tag`, and `cloud-run-push`. They use the working-tree root as context; check `.dockerignore` and the context contents rather than assuming secrets are excluded. For Cloud Build, provide the intended Dockerfile through an appropriate build configuration; `gcloud builds submit --tag` alone expects a root Dockerfile.

After pushing a tested image, resolve its immutable URI and update **both** jobs:

```bash
# Set IMAGE_URI to the reviewed us-central1-docker.pkg.dev/...@sha256:... URI.
gcloud run jobs update realtime-ingest --project=whyline-denver   --region=us-central1 --image="$IMAGE_URI"
gcloud run jobs update realtime-load --project=whyline-denver   --region=us-central1 --image="$IMAGE_URI"
```

An existing job does not automatically resolve a newly pushed `:latest`. Preserve each job's existing identity, environment, secrets, retry limits, and resource configuration. The entrypoint load branch uses `tools.dbt_with_env`, so omitting `tools/` breaks processing even if the application package builds.

Verify the new digest in completed executions, not just job configuration. A shared dbt/model repair must reach the realtime image as well as GitHub checkout-based batch workflows.

## Workflow configuration

The nightly schedules request 08:00/09:00/09:30 UTC. They are not chained and can start late. The realtime workflow YAMLs have only `workflow_dispatch`; Cloud Scheduler handles recurring realtime work.

Workflow secret names used by configuration include `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_RAW`, `BQ_DATASET_STG`, `BQ_DATASET_MART`, `NOAA_CDO_TOKEN`, and `CENSUS_API_KEY`. A stored secret is ineffective unless mapped into the step that consumes it. Inspect names and bindings without exposing values.

For manual recovery, wait for successful ingestion before transformation/tests/export, then wait for export before DuckDB refresh. Dispatching one workflow does not establish the other stages completed.

## Frontend

Install/build using the lockfile (`npm ci`, `npm run build`). Set server-side `API_BASE_URL` to the Cloud Run origin, currently referenced as `https://whylinedenver-api-1058998667347.us-central1.run.app`. Do not put provider keys in `NEXT_PUBLIC_*` variables. Changing a server-side rewrite requires rebuilding/redeploying with the intended environment.

Confirm production branch/project/domain settings in Vercel when deploying; the repository alone does not prove deployment completion. The dashboard route is `/app`.

## Verification and rollback

Read back API revision/image, both job images, scheduler state, workflow results, actual mart dates/quality, exports, DuckDB content, and public results. Check freshness and health separately. Existing DuckDB connections, schema artifacts, caches, and lookups can require a fresh service process to see changed files/schema; decide from query evidence before restarting.

Retain the previous immutable image digest and revision before deployment. Roll back to that reviewed image/revision if needed; a code rollback does not revert already-written data. Never delete retained raw data as a routine rollback. Use [QA validation](../QA_Validation_Guide.md).
