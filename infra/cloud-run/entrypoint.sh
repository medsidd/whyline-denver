#!/usr/bin/env bash
set -exuo pipefail

: "${JOB_TYPE:?JOB_TYPE must be set (load or stream)}"
SYNC_STATE_GCS_BLOB=${SYNC_STATE_GCS_BLOB:-state/sync_state.json}

export SYNC_STATE_GCS_BLOB

log() {
  printf '[%s] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

log "Starting Cloud Run job type=${JOB_TYPE}"

case "${JOB_TYPE}" in
  stream)
    : "${GCS_BUCKET:?GCS_BUCKET must be set}"
    : "${ARCHIVE_BUCKET:?ARCHIVE_BUCKET must be set}"
    log "Running continuous GTFS-RT stream bucket=${GCS_BUCKET} archive=${ARCHIVE_BUCKET}"
    # exec so SIGTERM from docker stop reaches Python, which checkpoints before exiting
    exec python -m whyline.ingest.gtfs_rt_stream --gcs \
      --bucket "${GCS_BUCKET}" \
      --archive-bucket "${ARCHIVE_BUCKET}" \
      --state-dir "${STATE_DIR:-/state}"
    ;;
  load)
    # Service alerts and Veo vehicles ride along every 15 minutes; a failed fetch must not
    # block the load.
    log "Snapshotting service alerts and Veo vehicles"
    python -m whyline.ingest.gtfs_alerts --gcs --bucket "${GCS_BUCKET:-whylinedenver-raw}" || log "ALERTS_INGEST_FAILED"
    python -m whyline.ingest.gbfs_veo --gcs --bucket "${GCS_BUCKET:-whylinedenver-raw}" || log "VEO_INGEST_FAILED"
    log "Running BigQuery load + realtime marts"
    make bq-load-realtime
    make dbt-run-realtime
    log "Updating BigQuery freshness timestamp"
    mkdir -p data
    make update-bq-timestamp
    ;;
  *)
    log "Unknown JOB_TYPE: ${JOB_TYPE}"
    exit 1
    ;;
esac

log "Completed Cloud Run job type=${JOB_TYPE}"
