#!/usr/bin/env bash
set -exuo pipefail

JOB_TYPE=${JOB_TYPE:-ingest}
SYNC_STATE_GCS_BLOB=${SYNC_STATE_GCS_BLOB:-state/sync_state.json}

export SYNC_STATE_GCS_BLOB

log() {
  printf '[%s] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

log "Starting Cloud Run job type=${JOB_TYPE}"

case "${JOB_TYPE}" in
  ingest)
    : "${GCS_BUCKET:?GCS_BUCKET must be set}"
    SNAPSHOTS="${GTFS_SNAPSHOTS:-1}"
    INTERVAL="${GTFS_INTERVAL_SEC:-120}"
    EXTRA_FLAGS="${GTFS_EXTRA_FLAGS:-}"
    log "Running GTFS-RT ingest snapshots=${SNAPSHOTS} interval=${INTERVAL}s bucket=${GCS_BUCKET} extra_flags='${EXTRA_FLAGS}'"
    CMD=(python -m whylinedenver.ingest.gtfs_realtime
      --gcs \
      --bucket "${GCS_BUCKET}" \
      --snapshots "${SNAPSHOTS}" \
      --interval-sec "${INTERVAL}")
    if [ -n "${EXTRA_FLAGS}" ]; then
      # shellcheck disable=SC2206
      EXTRA_ARRAY=(${EXTRA_FLAGS})
      CMD+=("${EXTRA_ARRAY[@]}")
    fi
    "${CMD[@]}"
    ;;
  load)
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
