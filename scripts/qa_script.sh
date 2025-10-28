#!/usr/bin/env bash
# Comprehensive QA Validation for WhyLine Denver Data Pipelines
# Runs all checks: GitHub Actions, GCS, BigQuery, DuckDB
# Usage: ./scripts/qa_comprehensive.sh [--skip-duckdb] [--skip-gcs]

set -euo pipefail

# Configuration
PROJECT="whyline-denver"
RAW_DATASET="raw_denver"
STG_DATASET="stg_denver"
MART_DATASET="mart_denver"
BUCKET="${GCS_BUCKET:-whylinedenver-raw}"
DUCKDB_PATH="${DUCKDB_PATH:-data/warehouse.duckdb}"

# Parse arguments
SKIP_DUCKDB=false
SKIP_GCS=false
for arg in "$@"; do
    case $arg in
        --skip-duckdb) SKIP_DUCKDB=true ;;
        --skip-gcs) SKIP_GCS=true ;;
    esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Score tracking
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Helper functions
check_passed() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

check_failed() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    echo -e "${RED}❌ FAIL${NC}: $1"
}

check_warning() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    WARNING_CHECKS=$((WARNING_CHECKS + 1))
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

section_header() {
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}$1${NC}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

subsection_header() {
    echo ""
    echo -e "${BOLD}${BLUE}▶ $1${NC}"
    echo ""
}

# Header
clear
echo -e "${BOLD}${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          WhyLine Denver - Comprehensive QA Validation         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Project:  ${PROJECT}"
echo "Datasets: ${RAW_DATASET}, ${STG_DATASET}, ${MART_DATASET}"
echo "Bucket:   ${BUCKET}"
echo ""

# ============================================================================
# SECTION 1: GitHub Actions Workflow Status
# ============================================================================
section_header "1. GitHub Actions Workflow Status"

if command -v gh &> /dev/null; then
    subsection_header "1.1 Nightly Ingest Workflow (Static Data)"

    # Check if workflow exists and get recent runs
    NIGHTLY_RUNS=$(gh run list --workflow=nightly-ingest.yml --limit 5 --json conclusion,status 2>/dev/null || echo "")

    if [ -z "$NIGHTLY_RUNS" ] || [ "$NIGHTLY_RUNS" = "[]" ]; then
        check_warning "Nightly ingest: No runs found (workflow may not exist yet)"
    else
        NIGHTLY_SUCCESS=$(echo "$NIGHTLY_RUNS" | jq -r '.[0].conclusion' 2>/dev/null || echo "unknown")
        if [ "$NIGHTLY_SUCCESS" = "success" ]; then
            check_passed "Nightly ingest: Latest run succeeded"
        elif [ "$NIGHTLY_SUCCESS" = "failure" ]; then
            check_failed "Nightly ingest: Latest run failed"
        else
            check_warning "Nightly ingest: Latest run status is '$NIGHTLY_SUCCESS'"
        fi

        # Show recent runs
        echo "Recent runs:"
        gh run list --workflow=nightly-ingest.yml --limit 3 --json conclusion,createdAt,displayTitle \
            --jq '.[] | "  \(.createdAt | split("T")[0]) - \(.conclusion)"' 2>/dev/null || echo "  (unable to fetch)"
    fi

    subsection_header "1.2 Realtime GTFS-RT Snapshots"

    HOURLY_RT_RUNS=$(gh run list --workflow=realtime-gtfs-rt.yml --limit 10 --json conclusion,status 2>/dev/null || echo "")

    if [ -z "$HOURLY_RT_RUNS" ] || [ "$HOURLY_RT_RUNS" = "[]" ]; then
        check_warning "Realtime GTFS-RT: No runs found yet (may not have triggered)"
    else
        # Count successes in last 10 runs
        SUCCESS_COUNT=$(echo "$HOURLY_RT_RUNS" | jq '[.[] | select(.conclusion == "success")] | length' 2>/dev/null || echo "0")
        TOTAL_COUNT=$(echo "$HOURLY_RT_RUNS" | jq 'length' 2>/dev/null || echo "0")

        # Calculate success rate
        if [ "$TOTAL_COUNT" -gt 0 ]; then
            SUCCESS_RATE=$((SUCCESS_COUNT * 100 / TOTAL_COUNT))
        else
            SUCCESS_RATE=0
        fi

        if [ "$SUCCESS_RATE" -ge 80 ]; then
            check_passed "Realtime GTFS-RT: ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%)"
        elif [ "$SUCCESS_RATE" -ge 50 ]; then
            check_warning "Realtime GTFS-RT: ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%, some failures)"
        else
            check_failed "Realtime GTFS-RT: Only ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%)"
        fi

        echo "Recent runs:"
        gh run list --workflow=realtime-gtfs-rt.yml --limit 5 --json conclusion,createdAt \
            --jq '.[] | "  \(.createdAt | split("T")[1] | split(".")[0]) - \(.conclusion)"' 2>/dev/null || echo "  (unable to fetch)"
    fi

    subsection_header "1.3 Realtime BigQuery Loads"

    HOURLY_BQ_RUNS=$(gh run list --workflow=realtime-bq-load.yml --limit 10 --json conclusion,status 2>/dev/null || echo "")

    if [ -z "$HOURLY_BQ_RUNS" ] || [ "$HOURLY_BQ_RUNS" = "[]" ]; then
        check_warning "Realtime BQ load: No runs found yet (may not have triggered)"
    else
        SUCCESS_COUNT=$(echo "$HOURLY_BQ_RUNS" | jq '[.[] | select(.conclusion == "success")] | length' 2>/dev/null || echo "0")
        TOTAL_COUNT=$(echo "$HOURLY_BQ_RUNS" | jq 'length' 2>/dev/null || echo "0")

        # Calculate success rate
        if [ "$TOTAL_COUNT" -gt 0 ]; then
            SUCCESS_RATE=$((SUCCESS_COUNT * 100 / TOTAL_COUNT))
        else
            SUCCESS_RATE=0
        fi

        if [ "$SUCCESS_RATE" -ge 80 ]; then
            check_passed "Realtime BQ load: ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%)"
        elif [ "$SUCCESS_RATE" -ge 50 ]; then
            check_warning "Realtime BQ load: ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%, some failures)"
        else
            check_failed "Realtime BQ load: Only ${SUCCESS_COUNT}/${TOTAL_COUNT} runs succeeded (${SUCCESS_RATE}%)"
        fi

        echo "Recent runs:"
        gh run list --workflow=realtime-bq-load.yml --limit 5 --json conclusion,createdAt \
            --jq '.[] | "  \(.createdAt | split("T")[1] | split(".")[0]) - \(.conclusion)"' 2>/dev/null || echo "  (unable to fetch)"
    fi
else
    check_warning "GitHub CLI (gh) not installed - skipping workflow checks"
    echo "Install with: brew install gh"
fi

# ============================================================================
# SECTION 2: GCS Raw Files Validation
# ============================================================================
if [ "$SKIP_GCS" = false ]; then
    section_header "2. GCS Raw Files Validation"

    if command -v gsutil &> /dev/null; then
        TODAY=$(date +%Y%m%d)

        subsection_header "2.1 GTFS-RT Trip Updates Files (Today)"

        # Check if files exist for today (partition format: snapshot_at=YYYY-MM-DDT*)
        TODAY_ISO=$(date -u +%Y-%m-%d)
        RT_SNAPSHOTS=$(gsutil ls "gs://${BUCKET}/raw/rtd_gtfsrt/" 2>/dev/null | grep "snapshot_at=${TODAY_ISO}" | wc -l)
        RT_SNAPSHOTS=$(echo "$RT_SNAPSHOTS" | tr -d '\n' | tr -d ' ')  # Remove newlines and spaces

        if [ -z "$RT_SNAPSHOTS" ]; then
            RT_SNAPSHOTS=0
        fi

        if [ "$RT_SNAPSHOTS" -eq 0 ]; then
            check_warning "GTFS-RT snapshots: No snapshot directories found for today (${TODAY_ISO})"
        elif [ "$RT_SNAPSHOTS" -ge 200 ]; then
            check_passed "GTFS-RT snapshots: ${RT_SNAPSHOTS} snapshot directories for today (expected ~96)"
        elif [ "$RT_SNAPSHOTS" -ge 100 ]; then
            check_warning "GTFS-RT snapshots: ${RT_SNAPSHOTS} directories (expected ~96, day may still be in progress)"
        elif [ "$RT_SNAPSHOTS" -ge 10 ]; then
            check_warning "GTFS-RT snapshots: ${RT_SNAPSHOTS} directories (micro-batch flow may have started recently)"
        else
            check_failed "GTFS-RT snapshots: Only ${RT_SNAPSHOTS} directories (expected at least double digits)"
        fi

        # Show recent snapshots
        echo "Recent snapshot directories:"
        gsutil ls "gs://${BUCKET}/raw/rtd_gtfsrt/" 2>/dev/null | grep "snapshot_at=${TODAY_ISO}" | tail -5 || echo "  (none found)"

        subsection_header "2.2 Weather Data Files"

        # Check weather extract directories
        WEATHER_EXTRACTS=$(gsutil ls "gs://${BUCKET}/raw/noaa_daily/" 2>/dev/null | grep "extract_date=" | wc -l)
        WEATHER_EXTRACTS=$(echo "$WEATHER_EXTRACTS" | tr -d '\n' | tr -d ' ')  # Remove newlines and spaces

        if [ -z "$WEATHER_EXTRACTS" ]; then
            WEATHER_EXTRACTS=0
        fi

        if [ "$WEATHER_EXTRACTS" -gt 0 ]; then
            check_passed "Weather extracts: ${WEATHER_EXTRACTS} extract dates found"
            echo "Most recent extracts:"
            gsutil ls "gs://${BUCKET}/raw/noaa_daily/" 2>/dev/null | grep "extract_date=" | tail -5 || echo "  (none)"
        else
            check_warning "Weather extracts: No extract directories found"
        fi
    else
        check_warning "gsutil not installed - skipping GCS checks"
        echo "Install with: gcloud components install gsutil"
    fi
else
    section_header "2. GCS Raw Files Validation [SKIPPED]"
fi

# ============================================================================
# SECTION 3: BigQuery Raw Tables
# ============================================================================
section_header "3. BigQuery Raw Tables Validation"

subsection_header "3.1 GTFS-RT Trip Updates: Today's Snapshot Count"

SNAPSHOT_RESULT=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  COUNT(DISTINCT feed_ts_utc) AS num_snapshots,
  COUNT(*) AS total_updates
FROM \`${PROJECT}.${RAW_DATASET}.raw_gtfsrt_trip_updates\`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver');
EOF
)

NUM_SNAPSHOTS=$(echo "$SNAPSHOT_RESULT" | tail -1 | cut -d',' -f1)
TOTAL_UPDATES=$(echo "$SNAPSHOT_RESULT" | tail -1 | cut -d',' -f2)

echo "Snapshots today: ${NUM_SNAPSHOTS}"
echo "Trip updates today: ${TOTAL_UPDATES}"

if [ "$NUM_SNAPSHOTS" -ge 280 ]; then
    check_passed "Snapshot count: ${NUM_SNAPSHOTS} (target: ~288)"
elif [ "$NUM_SNAPSHOTS" -ge 200 ]; then
    check_warning "Snapshot count: ${NUM_SNAPSHOTS} (target: ~288, day may still be accumulating)"
elif [ "$NUM_SNAPSHOTS" -ge 80 ]; then
    check_warning "Snapshot count: ${NUM_SNAPSHOTS} (realtime workflows may have started recently)"
else
    check_failed "Snapshot count: ${NUM_SNAPSHOTS} (expected at least 80)"
fi

subsection_header "3.2 GTFS-RT Trip Updates: 7-Day Trend"

echo "Last 7 days:"
bq query --nouse_legacy_sql --format=pretty --max_rows=7 << EOF
SELECT
  DATE(feed_ts_utc, 'America/Denver') AS date_mst,
  COUNT(DISTINCT feed_ts_utc) AS snapshots,
  COUNT(*) AS trip_updates
FROM \`${PROJECT}.${RAW_DATASET}.raw_gtfsrt_trip_updates\`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY date_mst
ORDER BY date_mst DESC;
EOF

# Check if we have data
TREND_CHECK=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT COUNT(DISTINCT DATE(feed_ts_utc)) AS days_with_data
FROM \`${PROJECT}.${RAW_DATASET}.raw_gtfsrt_trip_updates\`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY);
EOF
)

DAYS_WITH_DATA=$(echo "$TREND_CHECK" | tail -1)

if [ "$DAYS_WITH_DATA" -ge 3 ]; then
    check_passed "7-day trend: Data found for ${DAYS_WITH_DATA} days"
else
    check_warning "7-day trend: Only ${DAYS_WITH_DATA} days with data"
fi

subsection_header "3.3 GTFS-RT: Missing Hours Check"

MISSING_HOURS=$(bq query --nouse_legacy_sql --format=csv << EOF
WITH expected_hours AS (
  SELECT hour FROM UNNEST(GENERATE_ARRAY(0, 23)) AS hour
),
actual_hours AS (
  SELECT DISTINCT EXTRACT(HOUR FROM DATETIME(feed_ts_utc, 'America/Denver')) AS hour
  FROM \`${PROJECT}.${RAW_DATASET}.raw_gtfsrt_trip_updates\`
  WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
)
SELECT e.hour AS missing_hour_mst
FROM expected_hours e
LEFT JOIN actual_hours a ON e.hour = a.hour
WHERE a.hour IS NULL
ORDER BY e.hour;
EOF
)

MISSING_COUNT=$(echo "$MISSING_HOURS" | tail -n +2 | wc -l)

if [ "$MISSING_COUNT" -eq 0 ]; then
    check_passed "Realtime coverage: All hours captured (24h span)"
else
    check_warning "Realtime coverage: ${MISSING_COUNT} hours missing"
    echo "Missing hours:"
    echo "$MISSING_HOURS" | tail -n +2
fi

subsection_header "3.4 GTFS-RT Vehicle Positions Check"

VP_RESULT=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  COUNT(*) AS total_positions,
  COUNT(DISTINCT vehicle_id) AS unique_vehicles,
  COUNT(DISTINCT feed_ts_utc) AS num_snapshots
FROM \`${PROJECT}.${RAW_DATASET}.raw_gtfsrt_vehicle_positions\`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver');
EOF
)

VP_COUNT=$(echo "$VP_RESULT" | tail -1 | cut -d',' -f1)
VP_VEHICLES=$(echo "$VP_RESULT" | tail -1 | cut -d',' -f2)
VP_SNAPSHOTS=$(echo "$VP_RESULT" | tail -1 | cut -d',' -f3)

echo "Vehicle positions today: ${VP_COUNT}"
echo "Unique vehicles: ${VP_VEHICLES}"
echo "Snapshots: ${VP_SNAPSHOTS}"

if [ "$VP_COUNT" -gt 100000 ]; then
    check_passed "Vehicle positions: ${VP_COUNT} records (expected ~110,000/day)"
elif [ "$VP_COUNT" -gt 30000 ]; then
    check_warning "Vehicle positions: ${VP_COUNT} records (day may not be complete)"
else
    check_warning "Vehicle positions: ${VP_COUNT} records (realtime workflows may not have ramped yet)"
fi

subsection_header "3.5 NOAA Weather Data"

echo "Weather data (last 30 days, recent data expected to have NULLs due to NOAA lag):"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  MAX(date) AS latest_date,
  DATE_DIFF(CURRENT_DATE('America/Denver'), MAX(date), DAY) AS days_behind,
  COUNT(DISTINCT date) AS days_covered,
  COUNTIF(precip_mm IS NOT NULL) AS days_with_precip_data,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) AS pct_recent_coverage
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
EOF

echo ""
echo "Weather data quality (data >14 days old, should be finalized):"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  COUNT(DISTINCT date) AS days_covered,
  COUNTIF(precip_mm IS NOT NULL) AS days_with_complete_data,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) AS pct_complete
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND date <= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 14 DAY);
EOF

WEATHER_CHECK=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  DATE_DIFF(CURRENT_DATE('America/Denver'), MAX(date), DAY) AS days_behind,
  COUNT(DISTINCT date) AS days_covered
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
EOF
)

WEATHER_DAYS_BEHIND=$(echo "$WEATHER_CHECK" | tail -1 | cut -d',' -f1)
WEATHER_DAYS_COVERED=$(echo "$WEATHER_CHECK" | tail -1 | cut -d',' -f2)

if [ "$WEATHER_DAYS_BEHIND" -le 7 ]; then
    check_passed "Weather data freshness: ${WEATHER_DAYS_BEHIND} days behind (excellent, within expected 3-7 day lag)"
else
    check_warning "Weather data freshness: ${WEATHER_DAYS_BEHIND} days behind (may need manual backfill)"
fi

if [ "$WEATHER_DAYS_COVERED" -ge 25 ]; then
    check_passed "Weather date range: ${WEATHER_DAYS_COVERED}/30 days available"
else
    check_warning "Weather date range: ${WEATHER_DAYS_COVERED}/30 days available (expected ~30)"
fi

# Check finalized data quality (convert float to int for bash comparison)
FINALIZED_CHECK=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  CAST(ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 0) AS INT64) AS pct_complete
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND date <= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 14 DAY);
EOF
)

FINALIZED_PCT=$(echo "$FINALIZED_CHECK" | tail -1)

# Ensure it's an integer
FINALIZED_PCT=$(printf "%.0f" "$FINALIZED_PCT" 2>/dev/null || echo "0")

if [ "$FINALIZED_PCT" -ge 70 ]; then
    check_passed "Weather data quality: ${FINALIZED_PCT}% complete (finalized data >14 days old)"
elif [ "$FINALIZED_PCT" -ge 50 ]; then
    check_warning "Weather data quality: ${FINALIZED_PCT}% complete (some gaps in finalized data)"
elif [ "$FINALIZED_PCT" -ge 20 ]; then
    check_warning "Weather data quality: ${FINALIZED_PCT}% complete (backfill may be incomplete)"
else
    check_warning "Weather data quality: ${FINALIZED_PCT}% complete (significant gaps, check backfill)"
fi

subsection_header "3.6 Weather Precipitation Distribution"

echo "Precipitation bins (last 90 days):"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  precip_bin,
  COUNT(*) AS num_days,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER() * 100, 1) AS pct_of_days
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND precip_bin IS NOT NULL
GROUP BY precip_bin
ORDER BY
  CASE precip_bin
    WHEN 'none' THEN 1
    WHEN 'light' THEN 2
    WHEN 'mod' THEN 3
    WHEN 'heavy' THEN 4
  END;
EOF

PRECIP_BINS=$(bq query --nouse_legacy_sql --format=csv << EOF
SELECT COUNT(DISTINCT precip_bin) AS num_bins
FROM \`${PROJECT}.${RAW_DATASET}.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND precip_bin IS NOT NULL;
EOF
)

NUM_PRECIP_BINS=$(echo "$PRECIP_BINS" | tail -1)

if [ "$NUM_PRECIP_BINS" -ge 3 ]; then
    check_passed "Precipitation bins: ${NUM_PRECIP_BINS} bins found (includes rainy days)"
else
    check_warning "Precipitation bins: ${NUM_PRECIP_BINS} bins found (may be mostly dry)"
fi

# ============================================================================
# SECTION 4: BigQuery Staging Views
# ============================================================================
section_header "4. BigQuery Staging Views"

subsection_header "4.1 Staging RT Events: Freshness"

echo "RT Events (last 2 hours):"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  MAX(DATETIME(feed_ts_utc, 'America/Denver')) AS latest_snapshot_mst,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(feed_ts_utc), MINUTE) AS minutes_ago,
  COUNT(DISTINCT trip_id) AS unique_trips,
  COUNT(DISTINCT route_id) AS unique_routes,
  COUNT(*) AS total_events
FROM \`${PROJECT}.${STG_DATASET}.stg_rt_events\`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);
EOF

RT_FRESHNESS=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(feed_ts_utc), MINUTE) AS minutes_ago,
  COUNT(DISTINCT trip_id) AS unique_trips
FROM \`${PROJECT}.${STG_DATASET}.stg_rt_events\`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);
EOF
)

MINUTES_AGO=$(echo "$RT_FRESHNESS" | tail -1 | cut -d',' -f1)
UNIQUE_TRIPS=$(echo "$RT_FRESHNESS" | tail -1 | cut -d',' -f2)

# Check if we're in operating hours (5am-7pm MST = 12:00-02:00 UTC)
CURRENT_HOUR_UTC=$(date -u +%H)

if [ "$MINUTES_AGO" -lt 120 ]; then
    check_passed "RT Events freshness: ${MINUTES_AGO} minutes ago"
elif [ "$CURRENT_HOUR_UTC" -ge 3 ] && [ "$CURRENT_HOUR_UTC" -le 11 ]; then
    check_warning "RT Events freshness: ${MINUTES_AGO} minutes ago (outside operating hours, this is normal)"
else
    check_warning "RT Events freshness: ${MINUTES_AGO} minutes ago (may be stale)"
fi

subsection_header "4.2 Staging Weather Data"

echo "Weather (last 30 days):"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  MAX(date) AS latest_date,
  DATE_DIFF(CURRENT_DATE('America/Denver'), MAX(date), DAY) AS days_behind,
  COUNT(DISTINCT date) AS days_available
FROM \`${PROJECT}.${STG_DATASET}.stg_weather\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
EOF

WEATHER_STG=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT COUNT(DISTINCT date) AS days_available
FROM \`${PROJECT}.${STG_DATASET}.stg_weather\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
EOF
)

WEATHER_STG_DAYS=$(echo "$WEATHER_STG" | tail -1)

if [ "$WEATHER_STG_DAYS" -ge 25 ]; then
    check_passed "Staging weather: ${WEATHER_STG_DAYS} days available"
else
    check_warning "Staging weather: ${WEATHER_STG_DAYS} days available (expected ~30)"
fi

# ============================================================================
# SECTION 5: BigQuery Marts
# ============================================================================
section_header "5. BigQuery Marts"

subsection_header "5.1 Reliability by Route/Day"

echo "Reliability mart data range:"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  MIN(service_date_mst) AS first_date,
  MAX(service_date_mst) AS last_date,
  COUNT(DISTINCT service_date_mst) AS transit_days,
  COUNT(DISTINCT route_id) AS unique_routes,
  ROUND(AVG(pct_on_time) * 100, 1) AS avg_on_time_pct
FROM \`${PROJECT}.${MART_DATASET}.mart_reliability_by_route_day\`;
EOF

MART_CHECK=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  COUNT(DISTINCT service_date_mst) AS transit_days,
  COUNT(DISTINCT route_id) AS unique_routes
FROM \`${PROJECT}.${MART_DATASET}.mart_reliability_by_route_day\`;
EOF
)

TRANSIT_DAYS=$(echo "$MART_CHECK" | tail -1 | cut -d',' -f1)
UNIQUE_ROUTES=$(echo "$MART_CHECK" | tail -1 | cut -d',' -f2)

if [ "$TRANSIT_DAYS" -ge 30 ]; then
    check_passed "Reliability mart: ${TRANSIT_DAYS} days of data (sufficient for analysis)"
elif [ "$TRANSIT_DAYS" -ge 7 ]; then
    check_warning "Reliability mart: ${TRANSIT_DAYS} days of data (need 30+ for weather analysis)"
elif [ "$TRANSIT_DAYS" -ge 1 ]; then
    check_warning "Reliability mart: ${TRANSIT_DAYS} days of data (accumulating...)"
else
    check_failed "Reliability mart: No data found"
fi

subsection_header "5.2 Weather Impact Analysis"

echo "Weather impacts by precipitation:"
bq query --nouse_legacy_sql --format=pretty << EOF
SELECT
  precip_bin,
  COUNT(DISTINCT route_id) AS routes_analyzed,
  ROUND(AVG(pct_on_time_avg) * 100, 1) AS avg_on_time_pct,
  ROUND(AVG(delta_pct_on_time) * 100, 1) AS avg_impact_pct_points
FROM \`${PROJECT}.${MART_DATASET}.mart_weather_impacts\`
GROUP BY precip_bin
ORDER BY
  CASE precip_bin
    WHEN 'none' THEN 1
    WHEN 'light' THEN 2
    WHEN 'mod' THEN 3
    WHEN 'heavy' THEN 4
  END;
EOF

WEATHER_IMPACT_BINS=$(bq query --nouse_legacy_sql --format=csv << EOF
SELECT COUNT(DISTINCT precip_bin) AS num_bins
FROM \`${PROJECT}.${MART_DATASET}.mart_weather_impacts\`;
EOF
)

NUM_IMPACT_BINS=$(echo "$WEATHER_IMPACT_BINS" | tail -1)

if [ "$NUM_IMPACT_BINS" -ge 3 ]; then
    check_passed "Weather impacts: ${NUM_IMPACT_BINS} precipitation bins analyzed"
elif [ "$NUM_IMPACT_BINS" -eq 1 ]; then
    if [ "$TRANSIT_DAYS" -lt 30 ]; then
        check_warning "Weather impacts: Only 'none' bin (expected: need 30+ days + rainy days)"
    else
        check_warning "Weather impacts: Only 'none' bin (may be mostly dry weather)"
    fi
else
    check_warning "Weather impacts: ${NUM_IMPACT_BINS} bins (limited precipitation data)"
fi

subsection_header "5.3 Data Accumulation Progress"

echo "Transit vs Weather data overlap:"
bq query --nouse_legacy_sql --format=pretty << EOF
WITH transit_range AS (
  SELECT
    MIN(service_date_mst) AS first_date,
    MAX(service_date_mst) AS last_date,
    COUNT(DISTINCT service_date_mst) AS transit_days
  FROM \`${PROJECT}.${MART_DATASET}.mart_reliability_by_route_day\`
),
weather_range AS (
  SELECT
    MIN(date) AS first_date,
    MAX(date) AS last_date,
    COUNT(DISTINCT date) AS weather_days,
    COUNTIF(precip_bin != 'none') AS rainy_days
  FROM \`${PROJECT}.${STG_DATASET}.stg_weather\`
  WHERE date >= '2025-01-01'
)
SELECT
  'Transit Data' AS source,
  t.first_date,
  t.last_date,
  t.transit_days AS total_days,
  NULL AS rainy_days
FROM transit_range t
UNION ALL
SELECT
  'Weather Data',
  w.first_date,
  w.last_date,
  w.weather_days,
  w.rainy_days
FROM weather_range w;
EOF

# ============================================================================
# SECTION 6: DuckDB Local Validation
# ============================================================================
if [ "$SKIP_DUCKDB" = false ]; then
    section_header "6. DuckDB Local Database"

    if [ -f "$DUCKDB_PATH" ]; then
        subsection_header "6.1 DuckDB Marts Overview"

        echo "Note: DuckDB contains synced marts only (raw tables not included)"
        echo ""

        # Check what tables exist
        echo "Available marts:"
        duckdb "$DUCKDB_PATH" << 'EOF'
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'main'
  AND table_name LIKE 'mart_%'
ORDER BY table_name;
EOF

        # Check mart freshness
        MART_CHECK=$(duckdb "$DUCKDB_PATH" -csv << 'EOF'
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM mart_reliability_by_route_day;
EOF
)

        MART_DATE=$(echo "$MART_CHECK" | tail -1 | cut -d',' -f1)
        MART_DAYS=$(echo "$MART_CHECK" | tail -1 | cut -d',' -f2)
        MART_RECORDS=$(echo "$MART_CHECK" | tail -1 | cut -d',' -f3)

        echo ""
        echo "Mart reliability status:"
        echo "  Latest date: ${MART_DATE}"
        echo "  Days of data: ${MART_DAYS}"
        echo "  Total records: ${MART_RECORDS}"

        # Check if date is recent
        DAYS_OLD=$(( ($(date +%s) - $(date -j -f "%Y-%m-%d" "$MART_DATE" +%s 2>/dev/null || date -d "$MART_DATE" +%s)) / 86400 ))

        if [ "$DAYS_OLD" -le 1 ]; then
            check_passed "DuckDB mart freshness: Latest data is ${MART_DATE} (today or yesterday)"
        elif [ "$DAYS_OLD" -le 3 ]; then
            check_warning "DuckDB mart freshness: Latest data is ${MART_DATE} (${DAYS_OLD} days old)"
        else
            check_warning "DuckDB mart freshness: Latest data is ${MART_DATE} (${DAYS_OLD} days old, run 'make sync-duckdb')"
        fi

        subsection_header "6.2 DuckDB Mart Coverage"

        echo "Mart data by date:"
        duckdb "$DUCKDB_PATH" << 'EOF'
SELECT
  service_date_mst,
  COUNT(DISTINCT route_id) AS routes,
  COUNT(*) AS records
FROM mart_reliability_by_route_day
GROUP BY service_date_mst
ORDER BY service_date_mst DESC;
EOF

        subsection_header "6.3 Cross-Platform Consistency Check"

        echo "Note: Comparing marts (which are synced), not raw tables (which are snapshots)"
        echo ""

        # Get mart data from DuckDB
        DUCKDB_MART=$(duckdb "$DUCKDB_PATH" -csv << 'EOF'
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM mart_reliability_by_route_day;
EOF
)

        DUCKDB_DATE=$(echo "$DUCKDB_MART" | tail -1 | cut -d',' -f1)
        DUCKDB_DAYS=$(echo "$DUCKDB_MART" | tail -1 | cut -d',' -f2)
        DUCKDB_COUNT=$(echo "$DUCKDB_MART" | tail -1 | cut -d',' -f3)

        # Get mart data from BigQuery
        BQ_MART=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 << EOF
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM \`${PROJECT}.${MART_DATASET}.mart_reliability_by_route_day\`;
EOF
)

        BQ_DATE=$(echo "$BQ_MART" | tail -1 | cut -d',' -f1)
        BQ_DAYS=$(echo "$BQ_MART" | tail -1 | cut -d',' -f2)
        BQ_COUNT=$(echo "$BQ_MART" | tail -1 | cut -d',' -f3)

        echo "Mart reliability records:"
        echo "  BigQuery: ${BQ_COUNT} records, ${BQ_DAYS} days (latest: ${BQ_DATE})"
        echo "  DuckDB:   ${DUCKDB_COUNT} records, ${DUCKDB_DAYS} days (latest: ${DUCKDB_DATE})"

        # Check if dates match
        if [ "$BQ_DATE" = "$DUCKDB_DATE" ]; then
            check_passed "Mart sync: Latest date matches (${BQ_DATE})"

            # Calculate count difference
            if [ "$BQ_COUNT" -gt 0 ]; then
                DIFF=$((BQ_COUNT - DUCKDB_COUNT))
                if [ "$DIFF" -lt 0 ]; then
                    DIFF=$((-DIFF))
                fi
                PCT_DIFF=$((DIFF * 100 / BQ_COUNT))

                if [ "$PCT_DIFF" -le 5 ]; then
                    check_passed "Record count consistency: ${PCT_DIFF}% difference (excellent)"
                elif [ "$PCT_DIFF" -le 20 ]; then
                    check_warning "Record count consistency: ${PCT_DIFF}% difference (acceptable for incremental mart)"
                else
                    check_warning "Record count consistency: ${PCT_DIFF}% difference (run 'make sync-duckdb' to refresh)"
                fi
            fi
        else
            check_warning "Mart sync: Date mismatch (BQ: ${BQ_DATE}, DuckDB: ${DUCKDB_DATE}) - run 'make sync-duckdb'"
        fi

    else
        check_warning "DuckDB database not found at ${DUCKDB_PATH}"
    fi
else
    section_header "6. DuckDB Local Database [SKIPPED]"
fi

# ============================================================================
# FINAL SUMMARY
# ============================================================================
section_header "7. QA Summary & Recommendations"

echo ""
echo -e "${BOLD}Overall Results:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}✅ Passed:  ${PASSED_CHECKS}${NC}"
echo -e "  ${YELLOW}⚠️  Warnings: ${WARNING_CHECKS}${NC}"
echo -e "  ${RED}❌ Failed:  ${FAILED_CHECKS}${NC}"
echo -e "  ${BOLD}Total:    ${TOTAL_CHECKS}${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Calculate success rate
if [ "$TOTAL_CHECKS" -gt 0 ]; then
    SUCCESS_RATE=$(( (PASSED_CHECKS * 100) / TOTAL_CHECKS ))

    if [ "$SUCCESS_RATE" -ge 90 ]; then
        echo -e "${GREEN}${BOLD}✅ SUCCESS RATE: ${SUCCESS_RATE}% - System is healthy!${NC}"
    elif [ "$SUCCESS_RATE" -ge 70 ]; then
        echo -e "${YELLOW}${BOLD}⚠️  SUCCESS RATE: ${SUCCESS_RATE}% - Some issues need attention${NC}"
    else
        echo -e "${RED}${BOLD}❌ SUCCESS RATE: ${SUCCESS_RATE}% - Significant issues detected${NC}"
    fi
fi

echo ""
echo -e "${BOLD}Expected State:${NC}"
echo "  • After realtime workflows launch (Day 1):"
echo "    - Double-digit snapshots captured as cadence ramps up"
echo "    - Missing hours are NORMAL on Day 1 (micro-batch only active post-launch)"
echo "    - By tomorrow evening: ~288 snapshots/day"
echo ""
echo "  • Steady state (Day 2+):"
echo "    - 288 snapshots/day (every 5 minutes)"
echo "    - ≈600,000 trip updates/day"
echo "    - ≈110,000 vehicle positions/day"
echo "    - Zero missing hours (24-hour coverage)"
echo ""
echo "  • Weather data lag: 3-7 days (normal due to NOAA finalization)"
echo "  • Weather impact analysis: Needs 30+ days of transit data"
echo "  • DuckDB sync: Run 'make sync-duckdb' to update local database from BigQuery"
echo ""

if [ "$TRANSIT_DAYS" -lt 30 ]; then
    DAYS_REMAINING=$((30 - TRANSIT_DAYS))
    TARGET_DATE=$(date -v+${DAYS_REMAINING}d +%Y-%m-%d 2>/dev/null || date -d "+${DAYS_REMAINING} days" +%Y-%m-%d)
    echo -e "${YELLOW}${BOLD}⏱  Data Accumulation in Progress:${NC}"
    echo "  • Current transit data: ${TRANSIT_DAYS} days"
    echo "  • Days until sufficient data: ${DAYS_REMAINING}"
    echo "  • Target date: ${TARGET_DATE}"
    echo "  • Re-run this script after target date for full weather analysis"
    echo ""
fi

echo -e "${BOLD}For detailed documentation:${NC}"
echo "  • Complete validation guide: docs/QA_Validation_Guide.md"
echo "  • GTFS-RT strategy: docs/guides/GTFS_RT_Strategy.md"
echo "  • NOAA strategy: docs/guides/NOAA_Data_Collection_Strategy.md"
echo ""

if [ "$FAILED_CHECKS" -gt 0 ]; then
    echo -e "${RED}${BOLD}⚠️  Action Required:${NC}"
    echo "  Run with verbose logging to investigate failures:"
    echo "    $0 2>&1 | tee qa_results.log"
    echo ""
fi

echo "QA validation completed at $(date)"
echo ""
