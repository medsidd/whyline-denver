# Streamlit Service Deployment Notes

The Streamlit app runs on Cloud Run and mounts the DuckDB warehouse from Cloud Storage
so the UI can swap between DuckDB and BigQuery engines without extra infrastructure.

## DuckDB Artifact Location

- **Bucket:** `gs://whylinedenver-raw`
- **Object:** `marts/duckdb/warehouse.duckdb`

The nightly `nightly-duckdb` GitHub Actions workflow refreshes mart exports, rebuilds
`warehouse.duckdb`, and uploads the artifact to the path above. Each run overwrites the
single blob so Cloud Run always sees the latest snapshot when the GCS Fuse volume mounts
`/mnt/duckdb/warehouse.duckdb`.

## Required IAM Roles

Run the Streamlit service with a dedicated service account (e.g. `streamlit-app@`), or
reuse an existing one, with the following project-level roles:

- `roles/storage.objectViewer` on `whylinedenver-raw` so the container can read the
  DuckDB blob via the Cloud Storage mount.
- `roles/bigquery.jobUser` to submit query jobs when the BigQuery engine is selected.
- `roles/bigquery.dataViewer` to read datasets referenced by the app.

Grant these roles before deploying the Cloud Run service to avoid cold-start failures
when the app attempts to read the warehouse or issue BigQuery queries.
