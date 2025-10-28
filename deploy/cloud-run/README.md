# Cloud Run deployment for realtime pipelines

This directory contains everything required to run the GTFS realtime ingest and load
pipelines on **Cloud Run Jobs** triggered by **Cloud Scheduler**. Running in Cloud Run keeps
the hosted execution within the Google Cloud free tier while maintaining the five-minute
cadence expected by the product.

The build produces a container whose entrypoint is `deploy/cloud-run/entrypoint.sh`.
`JOB_TYPE` switches between ingest and load behaviour at runtime.

## One-time setup

```bash
export PROJECT_ID="whyline-denver"
export REGION="us-central1"
export REPO="realtime-jobs"
SERVICE_ACCOUNT="realtime-jobs@${PROJECT_ID}.iam.gserviceaccount.com"

# Enable required services
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com

# (Optional) Create the Artifact Registry repo if it does not exist yet
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="WhyLine Denver realtime jobs"

# Create / configure the runtime service account
gcloud iam service-accounts create realtime-jobs --project "${PROJECT_ID}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/storage.objectAdmin
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/bigquery.dataEditor
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/run.invoker

# First-time creation of the Cloud Run jobs
IMAGE="whyline-denver-realtime:latest"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"

# Build & push an initial image so the jobs have something to reference
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --config deploy/cloud-run/cloudbuild.yaml \
  --substitutions=_IMAGE_URI="${IMAGE_URI}" \
  .

gcloud run jobs create realtime-ingest \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --set-env-vars JOB_TYPE=ingest,GCS_BUCKET=whylinedenver-raw \
  --max-retries 1

gcloud run jobs create realtime-load \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --set-env-vars JOB_TYPE=load,GCS_BUCKET=whylinedenver-raw,SYNC_STATE_GCS_BUCKET=whylinedenver-raw,SYNC_STATE_GCS_BLOB=state/sync_state.json \
  --max-retries 1
```

If the datasets, buckets, or dbt profile locations differ for your environment, adjust the
environment variables accordingly.
Setting `SYNC_STATE_GCS_BUCKET` ensures each run mirrors `data/sync_state.json` to GCS for
other services (like Streamlit) to read freshness data.

## Recurring deployment flow

```bash
# Configure environment for the build + deploy
export PROJECT_ID=whyline-denver
export REGION=us-central1
export REPO=realtime-jobs
export IMAGE=whyline-denver-realtime:latest
export IMAGE_URI=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}

# Build & push the latest image
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --config deploy/cloud-run/cloudbuild.yaml \
  --substitutions=_IMAGE_URI="${IMAGE_URI}" \
  .

# Update the Cloud Run jobs to use the new image
gcloud run jobs update realtime-ingest \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}"

gcloud run jobs update realtime-load \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account realtime-jobs@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars JOB_TYPE=load,GCS_BUCKET=whylinedenver-raw,SYNC_STATE_GCS_BUCKET=whylinedenver-raw,SYNC_STATE_GCS_BLOB=state/sync_state.json,GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET_RAW=raw_denver,BQ_DATASET_STG=stg_denver,BQ_DATASET_MART=mart_denver,DBT_PROFILES_DIR=/app/dbt/profiles

# Smoke-test both jobs
gcloud run jobs execute realtime-ingest --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute realtime-load   --project "${PROJECT_ID}" --region "${REGION}" --wait

# Refresh the Cloud Scheduler triggers
PROJECT_ID=whyline-denver
REGION=us-central1
SCHEDULER_SA="realtime-jobs@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud scheduler jobs delete realtime-ingest --project "${PROJECT_ID}" --location "${REGION}"
gcloud scheduler jobs delete realtime-load   --project "${PROJECT_ID}" --location "${REGION}"

INGEST_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/realtime-ingest:run"
LOAD_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/realtime-load:run"

gcloud scheduler jobs create http realtime-ingest \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --schedule "*/5 * * * *" \
  --http-method POST \
  --uri "${INGEST_URI}" \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"

gcloud scheduler jobs create http realtime-load \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --schedule "2-59/5 * * * *" \
  --http-method POST \
  --uri "${LOAD_URI}" \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
```

Cloud Scheduler invokes each Cloud Run job every five minutes; the two-minute offset
allows the ingest step to finish writing GCS files before the BigQuery load starts.

## Monitoring

All stdout/stderr is streamed to Cloud Logging automatically. The existing QA script
(`scripts/qa_script.sh`) continues to validate freshness and snapshot counts; thresholds
assume 288 snapshots per day (five-minute cadence).
