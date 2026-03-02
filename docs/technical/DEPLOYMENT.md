# Deployment

This document covers deploying the FastAPI service, realtime Cloud Run jobs, and the Next.js frontend to production.

---

## Overview

| Component | Platform | Deploy method |
|-----------|---------|--------------|
| FastAPI API | Cloud Run service (`whylinedenver-api`) | `make api-deploy` |
| Realtime ingest jobs | Cloud Run jobs (`realtime-ingest`, `realtime-load`) | `gcloud run jobs update` |
| Next.js frontend | Vercel | Auto-deploys on push to `main` |
| Nightly batch pipelines | GitHub Actions | Triggered by cron schedules |

---

## FastAPI Service

### One-time setup

1. Create the Artifact Registry repository:

```bash
make artifact-repo-create-api
```

2. Create the Cloud Run service (first deploy handles this automatically via `make api-deploy`).

3. Grant required roles to the API service account (`api-service@whyline-denver.iam.gserviceaccount.com`):
   - `roles/bigquery.dataViewer`
   - `roles/bigquery.jobUser`
   - `roles/storage.objectViewer` (for GCS-Fuse DuckDB access)
   - `roles/secretmanager.secretAccessor` (for Gemini API key)

### Deploying the API

```bash
GEMINI_API_KEY_SECRET=gemini-api-key:latest make api-deploy
```

This runs `make api-build` (builds and pushes to Artifact Registry) followed by `gcloud run deploy`.

The build config is in `infra/api-service/cloudbuild.yaml`. The Dockerfile is at `api/Dockerfile`.

**What the deployment does:**
1. Builds the Docker image with `gcloud builds submit`
2. Pushes to `us-central1-docker.pkg.dev/whyline-denver/api-service/whylinedenver-api:latest`
3. Deploys to Cloud Run with the environment variables in the make target
4. Mounts GCS bucket at `/mnt/gcs` via GCS-Fuse (for DuckDB access)

### Environment variables on Cloud Run

The API reads these at startup. In Cloud Run, set them as environment variables or Secret Manager references:

| Variable | Value in Cloud Run |
|----------|-------------------|
| `ENGINE` | `duckdb` (or `bigquery` for BigQuery-first) |
| `LLM_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | Set via `--set-secrets=GEMINI_API_KEY=gemini-api-key:latest` |
| `GCP_PROJECT_ID` | `whyline-denver` |
| `GCS_BUCKET` | `whylinedenver-raw` |
| `BQ_DATASET_RAW/STG/MART` | `raw_denver`, `stg_denver`, `mart_denver` |
| `DUCKDB_PATH` | `/mnt/gcs/marts/duckdb/warehouse.duckdb` |
| `DUCKDB_COPY_LOCAL` | `1` (copy to /tmp for performance) |
| `DUCKDB_TEMP_DIR` | `/tmp` |
| `DBT_TARGET` | `prod` |

---

## Realtime Cloud Run Jobs

The realtime pipeline runs every 5 minutes via Cloud Scheduler triggering two Cloud Run jobs.

### One-time setup

1. Create the Artifact Registry repository for realtime jobs:

```bash
gcloud artifacts repositories create realtime-jobs \
  --repository-format=docker \
  --location=us-central1 \
  --project=whyline-denver
```

2. Create the Cloud Run jobs (first-time only):

```bash
gcloud run jobs create realtime-ingest \
  --image us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime:latest \
  --region us-central1 \
  --set-env-vars JOB_TYPE=ingest,GCS_BUCKET=whylinedenver-raw \
  --service-account realtime-jobs@whyline-denver.iam.gserviceaccount.com

gcloud run jobs create realtime-load \
  --image us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime:latest \
  --region us-central1 \
  --set-env-vars JOB_TYPE=load,GCS_BUCKET=whylinedenver-raw,GCP_PROJECT_ID=whyline-denver \
  --service-account realtime-jobs@whyline-denver.iam.gserviceaccount.com
```

3. Create Cloud Scheduler triggers (see `infra/cloud-run/README.md` for exact commands).

### Deploying a new image

```bash
# Build and push the image
make cloud-run-build    # gcloud builds submit using infra/cloud-run/cloudbuild.yaml
make cloud-run-push     # Tag and push to Artifact Registry

# Update running jobs to use new image
gcloud run jobs update realtime-ingest \
  --image us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime:latest \
  --region us-central1

gcloud run jobs update realtime-load \
  --image us-central1-docker.pkg.dev/whyline-denver/realtime-jobs/whylinedenver-realtime:latest \
  --region us-central1
```

**Important**: Cloud Run jobs do NOT auto-pull `:latest` when the image tag is updated. You must run the `gcloud run jobs update` commands explicitly after every image push.

### How the realtime image works

The image (`infra/cloud-run/Dockerfile`) runs `infra/cloud-run/entrypoint.sh`, which dispatches based on the `JOB_TYPE` environment variable:

- `JOB_TYPE=ingest`: Runs the GTFS-RT ingestor (`python -m whyline.ingest.gtfs_realtime --gcs ...`)
- `JOB_TYPE=load`: Runs `make bq-load-realtime && make dbt-run-realtime && make update-bq-timestamp`

---

## GitHub Actions Secrets

The CI/CD workflows read secrets from GitHub Actions repository secrets. Set these in **Settings → Secrets and variables → Actions**:

| Secret | Used by | Description |
|--------|---------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | All workflows | GCP service account JSON (inline) |
| `GCP_PROJECT_ID` | nightly-bq, nightly-ingest | GCP project ID |
| `GCS_BUCKET` | nightly-ingest, nightly-duckdb | GCS bucket name |
| `BQ_DATASET_RAW` | nightly-bq, nightly-ingest | BigQuery raw dataset |
| `BQ_DATASET_STG` | nightly-bq | BigQuery staging dataset |
| `BQ_DATASET_MART` | nightly-bq | BigQuery mart dataset |
| `NOAA_CDO_TOKEN` | nightly-ingest | NOAA Climate Data Online API token |
| `SYNC_STATE_GCS_BUCKET` | nightly-bq, nightly-duckdb | Sync state bucket |
| `SYNC_STATE_GCS_BLOB` | nightly-bq, nightly-duckdb | Sync state blob path |
| `DUCKDB_GCS_BLOB` | nightly-duckdb | DuckDB warehouse blob path |
| `DUCKDB_PARQUET_ROOT` | nightly-duckdb | Local Parquet cache path |
| `DBT_PROFILES_DIR` | nightly-bq | dbt profiles directory |

---

## GitHub Actions Workflows

| Workflow | Schedule | Trigger | What it runs |
|----------|----------|---------|-------------|
| `ci.yml` | On PR + push to `main` | Automatic | lint, pytest, dbt docs deploy to GitHub Pages |
| `nightly-ingest.yml` | 08:00 UTC daily | Schedule | `make nightly-ingest-bq` (7 ingestors + BQ load) |
| `nightly-bq.yml` | 09:00 UTC daily | Schedule | `make nightly-bq` (dbt full DAG + mart export) |
| `nightly-duckdb.yml` | 09:30 UTC daily | Schedule | `make nightly-duckdb` (DuckDB refresh) |
| `realtime-gtfs-rt.yml` | Manual only | `workflow_dispatch` | GTFS-RT snapshot (Cloud Run handles this in prod) |
| `realtime-bq-load.yml` | Manual only | `workflow_dispatch` | BQ load + dbt realtime (Cloud Run handles in prod) |

The realtime workflows are `workflow_dispatch` only — in production, Cloud Scheduler triggers Cloud Run jobs directly. The workflow files exist for manual testing and debugging.

---

## Frontend (Vercel)

### Setup

1. Connect the repository to Vercel
2. Set the environment variable in the Vercel project settings:
   - `API_BASE_URL` → Cloud Run API service URL (e.g., `https://whylinedenver-api-xxxx-uc.a.run.app`)
   - Do NOT prefix with `NEXT_PUBLIC_` — this variable is used server-side in `next.config.mjs` rewrites only

### How the proxy works

`next.config.mjs` rewrites all `/api/*` requests to `${API_BASE_URL}/api/*` server-side. The browser never sees the Cloud Run URL and there are no CORS issues.

### Manual build

```bash
make frontend-build   # next build — type-checks + compiles
```

### Deployment

Vercel auto-deploys on push to `main`. For manual deploy:

```bash
cd frontend && npx vercel --prod
```

---

## dbt Documentation Site

The CI workflow deploys dbt docs to GitHub Pages on every push to `main`. The site is available at `https://medsidd.github.io/whyline-denver/`.

To build locally:

```bash
make pages-build   # generates dbt docs + exports diagram SVGs
make dbt-docs      # serve dbt docs locally at localhost:8080
```
