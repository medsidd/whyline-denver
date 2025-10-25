#!/usr/bin/env bash
# Backfill NOAA weather data from Jan 2024 to Sep 2025
# This is a ONE-TIME operation to populate historical data

set -euo pipefail

echo "=== NOAA Historical Data Backfill ==="
echo ""

# Validate environment
if [ -z "${NOAA_CDO_TOKEN:-}" ]; then
  echo "❌ NOAA_CDO_TOKEN not set"
  echo "Run: export NOAA_CDO_TOKEN='your-token'"
  exit 1
fi

if [ -z "${GCS_BUCKET:-}" ]; then
  echo "❌ GCS_BUCKET not set"
  echo "Run: export GCS_BUCKET='your-bucket-name'"
  exit 1
fi

echo "✓ Token set (${#NOAA_CDO_TOKEN} chars)"
echo "✓ GCS Bucket: $GCS_BUCKET"
echo ""

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Working directory: $PROJECT_ROOT"
echo ""

# Function to run ingest with retry
run_ingest() {
  local start=$1
  local end=$2
  local extract=$3
  local quarter=$4

  echo "=== Backfilling $quarter ($start to $end) ==="

  PYTHONPATH="$PROJECT_ROOT/src" python -m whylinedenver.ingest.noaa_daily \
    --gcs --bucket "$GCS_BUCKET" \
    --start "$start" --end "$end" \
    --extract-date "$extract" || {
      echo "⚠️  Failed on first attempt, retrying in 5 seconds..."
      sleep 5
      PYTHONPATH="$PROJECT_ROOT/src" python -m whylinedenver.ingest.noaa_daily \
        --gcs --bucket "$GCS_BUCKET" \
        --start "$start" --end "$end" \
        --extract-date "$extract"
    }

  echo "✓ Completed $quarter"
  echo ""

  # Rate limiting: wait 2 seconds between requests
  sleep 2
}

# Backfill by quarter (avoids hitting API limits)
run_ingest "2024-01-01" "2024-03-31" "2024-03-31" "Q1 2024"
run_ingest "2024-04-01" "2024-06-30" "2024-06-30" "Q2 2024"
run_ingest "2024-07-01" "2024-09-30" "2024-09-30" "Q3 2024"
run_ingest "2024-10-01" "2024-12-31" "2024-12-31" "Q4 2024"

# 2025 data (more likely to have gaps)
run_ingest "2025-01-01" "2025-03-31" "2025-03-31" "Q1 2025"
run_ingest "2025-04-01" "2025-06-30" "2025-06-30" "Q2 2025"
run_ingest "2025-07-01" "2025-09-30" "2025-09-30" "Q3 2025"

echo "=== Backfill Complete ==="
echo ""
echo "Files uploaded to: gs://$GCS_BUCKET/raw/noaa_daily/"
echo ""
echo "Next steps:"
echo "  1. Load to BigQuery: make bq-load"
echo "  2. Run dbt: make nightly-bq"
