# Deployment

This is a deployment reference, not an instruction to start or redeploy resources during setup. Preserve retained data and inspect current state first. [Operations](OPERATIONS.md) contains the dated live snapshot; source configuration is not evidence of a completed deployment.

## Deployed components

| Component | Configuration/source |
|---|---|
| FastAPI Cloud Run service `whylinedenver-api` | `api/Dockerfile`, `infra/api-service/cloudbuild.yaml`, Makefile `api-build` / `api-deploy` |
| Cloud Run job `realtime-load` | Shared `infra/cloud-run/Dockerfile` and `entrypoint.sh`; `JOB_TYPE` (`load` or `stream`, required) selects behavior. The paused `realtime-ingest` job has no mode in the image any more |
| Cloud Scheduler | Calls the Run jobs API with an authorized identity; inspect actual schedules |
| Next.js on Vercel | `frontend/` build, server-side `API_BASE_URL` |
| Nightly workflows and CI | `.github/workflows/*.yml`; the three nightly workflows run as a chain. CI has a Python job and a frontend job (lint, unit specs, build) |
| Model documentation | CI generates dbt artifacts and publishes GitHub Pages on successful pushes to `main` |

Project: `whyline-denver`; region: `us-central1`; bucket: `whylinedenver-raw`. Cloudflare/domain/Vercel configuration is external to this repository; verify those settings before claiming automatic deployment behavior.

## API service

After reviewing the intended source and environment, an authorized API deployment uses:

```bash
make api-deploy
```

The Makefile pins the Gemini secret to version 1, the original key (`GEMINI_API_KEY_SECRET ?= gemini-api-key:1`; before November 19, 2026 it had to be passed by hand). A key created on November 18, 2026 (version 2) gets 404 for `gemini-2.5-flash` ("no longer available to new users"), and every newer Flash model answered 503 (high demand) that day. Move to `:latest` together with a `GEMINI_MODEL` that answers reliably for the new key.

This submits a Cloud Build, pushes `us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api:latest`, and deploys the service. Makefile defaults: 0–3 instances, concurrency 80, 2 CPUs, 2 GiB memory, gen2 execution environment, unauthenticated access, service identity `api-service@whyline-denver.iam.gserviceaccount.com`.

It sets Gemini as provider, the API query byte cap, and dataset/state locations, and maps the Gemini secret. `--set-env-vars` replaces the service's whole environment, and `--clear-volume-mounts --clear-volumes` remove any storage mount, so a deploy leaves no DuckDB settings or bucket mount behind (the API mounted the bucket for its DuckDB file until November 19, 2026). Prefer Secret Manager references over literal keys. The service account needs BigQuery job creation, reader access on `mart_denver` (and, until the live views are authorized views, on the datasets they read), read access to `state/sync_state.json` in the bucket for the freshness time, and access to the Gemini secret.

The image runs as the unprivileged user `app` (uid 10001), holds no dbt packages (the API reads the manifest and catalog as JSON), and writes only the query log under `/app/data/logs`. After a deploy, `GET /api/freshness` showing a time (not "Unavailable") confirms it can read the sync state.

Check usable manifest/catalog artifacts are included. `api/Dockerfile` consumes local artifacts; CI's generated artifacts do not automatically update a separately built API image. A healthy service without current artifacts may still fail `/api/models` or SQL generation.

## Realtime shared image

See [container reference](../../infra/cloud-run/README.md). Build from a clean reviewed source export containing `src/`, `dbt/`, `tools/`, `Makefile`, requirements, and `infra/cloud-run/`. Inspect included tracked files before uploading; exclude credentials, local raw data, generated artifacts, and unrelated work.

The Makefile offers `cloud-run-build` (local Docker), `cloud-run-tag`, and `cloud-run-push`. They use the working-tree root as context; check `.dockerignore` and the context contents rather than assuming secrets are excluded. For Cloud Build, provide the intended Dockerfile through an appropriate build configuration; `gcloud builds submit --tag` alone expects a root Dockerfile.

After pushing a tested image, resolve its immutable URI and update the job (and the poller VM's `image-uri`):

```bash
# Set IMAGE_URI to the reviewed us-central1-docker.pkg.dev/...@sha256:... URI.
gcloud run jobs update realtime-load --project=whyline-denver   --region=us-central1 --image="$IMAGE_URI"
```

An existing job does not automatically resolve a newly pushed `:latest`. Preserve each job's existing identity, environment, secrets, retry limits, and resource configuration. The entrypoint load branch uses `tools.dbt_with_env`, so omitting `tools/` breaks processing even if the application package builds.

Verify the new digest in completed executions, not just job configuration. A shared dbt/model repair must reach the realtime image as well as GitHub checkout-based batch workflows.

## Workflow configuration

Nightly Ingest requests 08:17 UTC (off the hour, which GitHub delays most) and can start hours late; Nightly BigQuery starts when it finishes. The realtime workflow YAML has only `workflow_dispatch`; Cloud Scheduler handles recurring realtime work.

Workflow secret names used by configuration include `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_RAW`, `BQ_DATASET_STG`, `BQ_DATASET_MART`, `NOAA_CDO_TOKEN`, and `CENSUS_API_KEY`. A stored secret is ineffective unless mapped into the step that consumes it. Inspect names and bindings without exposing values.

For manual recovery, dispatch Nightly Ingest; Nightly BigQuery follows it. Check both runs: dispatching one does not show the other completed.

## Frontend

Install/build using the lockfile (`npm ci`, `npm run build`). Set server-side `API_BASE_URL` to the Cloud Run origin, currently referenced as `https://whylinedenver-api-1058998667347.us-central1.run.app`. Do not put provider keys in `NEXT_PUBLIC_*` variables. Changing a server-side rewrite requires rebuilding/redeploying with the intended environment.

Confirm production branch/project/domain settings in Vercel when deploying; the repository alone does not prove deployment completion. The dashboard route is `/app`.

## Verification and rollback

Read back API revision/image, the job and VM images, scheduler state, workflow results, actual mart dates/quality and public results. Check freshness and health separately. Schema artifacts, caches and lookups can require a fresh service process to see a changed schema; decide from query evidence before restarting.

Retain the previous immutable image digest and revision before deployment. Roll back to that reviewed image/revision if needed; a code rollback does not revert already-written data. Never delete retained raw data as a routine rollback. Use [QA validation](../QA_Validation_Guide.md).
