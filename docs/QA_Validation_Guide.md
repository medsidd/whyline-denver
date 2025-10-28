# WhyLine Denver - QA Validation Documentation

**Last Updated**: October 24, 2025
**Script Location**: `scripts/qa_script.sh`

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Understanding the Output](#understanding-the-output)
4. [Validation Sections](#validation-sections)
5. [Expected Results by Stage](#expected-results-by-stage)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Query Reference](#query-reference)

---

## Overview

The QA validation script (`scripts/qa_script.sh`) is the **single source of truth** for validating the WhyLine Denver data pipeline. It checks:

- **GitHub Actions workflows** - Scheduled data ingestion jobs
- **GCS bucket files** - Raw data storage
- **BigQuery tables** - Data warehouse (raw → staging → marts)
- **DuckDB database** - Local analytical database (synced marts)
- **Cross-platform consistency** - BigQuery ↔ DuckDB sync validation

### When to Run This Script

Run the QA script anytime you want to verify pipeline health:

- ✅ **After deploying changes** to workflows or dbt models
- ✅ **Daily/weekly monitoring** to catch issues early
- ✅ **Before analysis** to ensure data quality
- ✅ **After re-running ingestion** to verify data completeness
- ✅ **Troubleshooting** when something seems wrong

### What It Validates

| Component | What's Checked |
|-----------|----------------|
| **GitHub Actions** | Workflow success rates, recent run status |
| **GCS Storage** | GTFS-RT snapshot files, weather data files |
| **BigQuery Raw** | Trip updates, vehicle positions, weather data coverage |
| **BigQuery Staging** | Staging view freshness, data availability |
| **BigQuery Marts** | Analytical tables, date ranges, data quality |
| **DuckDB** | Mart freshness, data coverage, sync consistency |

---

## Quick Start

### Run the Full QA Script

```bash
./scripts/qa_script.sh
```

### Configuration Options

The script uses these environment variables (with defaults):

```bash
# Google Cloud
export PROJECT="whyline-denver"
export RAW_DATASET="raw_denver"
export STG_DATASET="stg_denver"
export MART_DATASET="mart_denver"

# GCS
export GCS_BUCKET="whylinedenver-raw"

# DuckDB
export DUCKDB_PATH="data/warehouse.duckdb"

# Options
export SKIP_DUCKDB=false  # Set to true to skip DuckDB checks
```

### Skip DuckDB Validation

If you don't have DuckDB set up yet:

```bash
SKIP_DUCKDB=true ./scripts/qa_script.sh
```

---

## Understanding the Output

### Check Status Indicators

The script outputs three types of results:

| Symbol | Meaning | Action Needed |
|--------|---------|---------------|
| ✅ PASS | Check passed | None - working as expected |
| ⚠️ WARN | Warning - may be normal | Review context (often Day 1 behavior) |
| ❌ FAIL | Check failed | Investigate and fix |

### Success Rate

At the end, the script calculates an overall success rate:

```
Overall Results:
  ✅ Passed:  14
  ⚠️ Warnings: 6
  ❌ Failed:  0
  Total:    20

✅ SUCCESS RATE: 70% - System is healthy!
```

| Success Rate | Meaning |
|--------------|---------|
| **90-100%** | Excellent - steady state operation |
| **70-89%** | Good - some expected warnings (Day 1 behavior) |
| **50-69%** | Fair - needs attention |
| **<50%** | Poor - significant issues |

---

## Validation Sections

### Section 1: GitHub Actions Workflows

**What it checks**: Recent workflow runs and success rates

**Workflows validated**:
- `nightly-ingest.yml` - Static GTFS, weather, crash data (8am UTC daily)
- `realtime-gtfs-rt.yml` - Realtime snapshots (manual fallback; Cloud Run handles every 5 minutes)
- `realtime-bq-load.yml` - BigQuery loads + dbt micro-batch (offset ~2 min)

**Queries used**:
```bash
# Get recent workflow runs
gh run list --workflow=nightly-ingest.yml --limit 1 --json conclusion
gh run list --workflow=realtime-gtfs-rt.yml --limit 10 --json conclusion
gh run list --workflow=realtime-bq-load.yml --limit 10 --json conclusion
```

**Success criteria**:
- ✅ PASS: ≥80% success rate
- ⚠️ WARN: 50-79% success rate
- ❌ FAIL: <50% success rate

**Expected results**:
- **Day 1**: 4-10 runs (100% success)
- **Steady state**: 10/10 recent runs successful (100% success)

---

### Section 2: GCS Bucket Files

**What it checks**: Raw data files uploaded to Google Cloud Storage

**File types validated**:
- GTFS-RT snapshots (trip updates, vehicle positions)
- Weather data files

**Queries used**:
```bash
# Count GTFS-RT snapshots for today
TODAY_ISO=$(date -u +%Y-%m-%d)
gsutil ls "gs://${BUCKET}/raw/rtd_gtfsrt/" | grep "snapshot_at=${TODAY_ISO}" | wc -l

# Check weather file exists
gsutil ls "gs://${BUCKET}/raw/noaa_weather/date=${TODAY}/"
```

**Success criteria**:
- ✅ PASS: Weather file exists for today
- ⚠️ WARN: <240 GTFS-RT snapshots (normal on Day 1)
- ❌ FAIL: No snapshots or no weather file

**Expected results**:
- **Day 1**: 20-200 snapshots (micro-batch started mid-day)
- **Steady state**: ~288 snapshots/day (every 5 minutes)

---

### Section 3: BigQuery Raw Tables

**What it checks**: Raw data loaded into BigQuery

#### 3.1 GTFS-RT Snapshot Freshness

**Query**:
```sql
SELECT
  MAX(DATETIME(feed_ts_utc, 'America/Denver')) AS latest_snapshot_mst,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(feed_ts_utc), MINUTE) AS minutes_ago,
  COUNT(DISTINCT trip_id) AS unique_trips,
  COUNT(*) AS total_trip_updates
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);
```

**Success criteria**:
- ✅ PASS: Latest snapshot <20 minutes old
- ⚠️ WARN: 10-30 minutes old (temporary backlog)
- ❌ FAIL: >30 minutes old (outside maintenance window)

#### 3.2 Daily Snapshot Coverage

**Query**:
```sql
SELECT
  DATE(feed_ts_utc, 'America/Denver') AS snapshot_date,
  COUNT(DISTINCT feed_ts_utc) AS num_snapshots,
  COUNT(DISTINCT trip_id) AS unique_trips,
  COUNT(*) AS trip_updates
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY snapshot_date;
```

**Success criteria**:
- ✅ PASS: ≥240 snapshots today
- ⚠️ WARN: 120-239 snapshots (accumulating)
- ❌ FAIL: <120 snapshots

**Expected results**:
- **Day 1**: 20-200 snapshots, 100K-500K trip updates
- **Steady state**: 288 snapshots, ~600K trip updates/day

#### 3.3 Missing Hours Check

**Query**:
```sql
WITH windows AS (
  SELECT TIMESTAMP_ADD(
           TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY),
           INTERVAL offset MINUTE
         ) AS window_start
  FROM UNNEST(GENERATE_ARRAY(0, 24 * 60 - 5, 5)) AS offset
),
captured AS (
  SELECT DISTINCT TIMESTAMP_TRUNC(feed_ts_utc, MINUTE) AS minute_bucket
  FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
  WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
)
SELECT window_start
FROM windows w
LEFT JOIN captured c ON w.window_start = c.minute_bucket
WHERE c.minute_bucket IS NULL
ORDER BY window_start;
```

**Success criteria**:
- ✅ PASS: 0 missing 5-minute windows
- ⚠️ WARN: ≤24 missing windows (normal Day 1 warm-up)
- ❌ FAIL: >24 missing windows (after Day 2)

#### 3.4 Weather Data Freshness

**Query**:
```sql
SELECT
  MAX(date) AS latest_date,
  DATE_DIFF(CURRENT_DATE('America/Denver'), MAX(date), DAY) AS days_behind,
  COUNT(DISTINCT date) AS total_days
FROM `whyline-denver.raw_denver.raw_weather_daily`;
```

**Success criteria**:
- ✅ PASS: ≤7 days behind
- ⚠️ WARN: 8-14 days behind
- ❌ FAIL: >14 days behind

**Expected**: 1-7 days behind (NOAA has 3-7 day finalization lag)

#### 3.5 Weather Data Quality

**Query** (finalized data only):
```sql
SELECT
  COUNT(DISTINCT date) AS days_covered,
  COUNTIF(precip_mm IS NOT NULL) AS days_with_complete_data,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) AS pct_complete
FROM `whyline-denver.raw_denver.raw_weather_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND date <= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 14 DAY);
```

**Success criteria**:
- ✅ PASS: ≥70% complete (for data >14 days old)
- ⚠️ WARN: 50-69% complete
- ❌ FAIL: <50% complete

**Why >14 days old?** NOAA data is finalized 7-14 days after collection. Recent data will have NULLs.

#### 3.6 Weather Precipitation Distribution

**Query**:
```sql
SELECT
  precip_bin,
  COUNT(*) AS num_days,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER() * 100, 1) AS pct_of_days
FROM `whyline-denver.raw_denver.raw_weather_daily`
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
```

**Success criteria**:
- ✅ PASS: ≥3 precipitation bins (includes rainy days)
- ⚠️ WARN: Only 'none' bin (dry weather or limited data)

---

### Section 4: BigQuery Staging Views

**What it checks**: Staging views that clean and transform raw data

#### 4.1 Staging RT Events Freshness

**Query**:
```sql
SELECT
  MAX(DATETIME(feed_ts_utc, 'America/Denver')) AS latest_snapshot_mst,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(feed_ts_utc), MINUTE) AS minutes_ago,
  COUNT(DISTINCT trip_id) AS unique_trips,
  COUNT(DISTINCT route_id) AS unique_routes,
  COUNT(*) AS total_events
FROM `whyline-denver.stg_denver.stg_rt_events`
WHERE feed_ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);
```

**Success criteria**:
- ✅ PASS: <120 minutes old
- ⚠️ WARN: Outside operating hours (normal)

#### 4.2 Staging Weather Data

**Query**:
```sql
SELECT
  MAX(date) AS latest_date,
  DATE_DIFF(CURRENT_DATE('America/Denver'), MAX(date), DAY) AS days_behind,
  COUNT(DISTINCT date) AS days_available
FROM `whyline-denver.stg_denver.stg_weather`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
```

**Success criteria**:
- ✅ PASS: ≥25 days in last 30 days
- ⚠️ WARN: <25 days

---

### Section 5: BigQuery Marts

**What it checks**: Final analytical tables for dashboards and analysis

#### 5.1 Reliability by Route/Day

**Query**:
```sql
SELECT
  MIN(service_date_mst) AS first_date,
  MAX(service_date_mst) AS last_date,
  COUNT(DISTINCT service_date_mst) AS transit_days,
  COUNT(DISTINCT route_id) AS unique_routes,
  ROUND(AVG(pct_on_time) * 100, 1) AS avg_on_time_pct
FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`;
```

**Success criteria**:
- ✅ PASS: ≥30 days of data (sufficient for weather analysis)
- ⚠️ WARN: 7-29 days (accumulating)
- ⚠️ WARN: 1-6 days (just started)
- ❌ FAIL: No data

**Expected results**:
- **Day 1-2**: 1-2 days
- **After 30 days**: 30+ days (ready for weather impact analysis)

#### 5.2 Weather Impact Analysis

**Query**:
```sql
SELECT
  precip_bin,
  COUNT(DISTINCT route_id) AS routes_analyzed,
  ROUND(AVG(pct_on_time_avg) * 100, 1) AS avg_on_time_pct,
  ROUND(AVG(delta_pct_on_time) * 100, 1) AS avg_impact_pct_points
FROM `whyline-denver.mart_denver.mart_weather_impacts`
GROUP BY precip_bin
ORDER BY
  CASE precip_bin
    WHEN 'none' THEN 1
    WHEN 'light' THEN 2
    WHEN 'mod' THEN 3
    WHEN 'heavy' THEN 4
  END;
```

**Success criteria**:
- ✅ PASS: ≥3 precipitation bins
- ⚠️ WARN: Only 'none' bin (need rainy days for analysis)

**Why warnings?** Meaningful weather impact analysis requires:
- 30+ days of transit data
- Multiple rainy days for comparison
- Both dry and wet conditions

#### 5.3 Data Accumulation Progress

**Query**:
```sql
WITH transit_range AS (
  SELECT
    MIN(service_date_mst) AS first_date,
    MAX(service_date_mst) AS last_date,
    COUNT(DISTINCT service_date_mst) AS transit_days
  FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`
),
weather_range AS (
  SELECT
    MIN(date) AS first_date,
    MAX(date) AS last_date,
    COUNT(DISTINCT date) AS weather_days,
    COUNTIF(precip_bin != 'none') AS rainy_days
  FROM `whyline-denver.stg_denver.stg_weather`
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
```

**What it shows**: Overlap between transit and weather data for joint analysis

---

### Section 6: DuckDB Local Validation

**What it checks**: Local DuckDB database synced from BigQuery marts

**Important**: DuckDB contains **only mart tables**, not raw data. Use `make sync-duckdb` to refresh.

#### 6.1 DuckDB Marts Overview

**Queries**:
```sql
-- List available marts
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'main'
  AND table_name LIKE 'mart_%'
ORDER BY table_name;

-- Check mart freshness
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM mart_reliability_by_route_day;
```

**Success criteria**:
- ✅ PASS: Latest data from today or yesterday
- ⚠️ WARN: 2-3 days old
- ⚠️ WARN: >3 days old (run `make sync-duckdb`)

**Expected marts**:
1. mart_access_score_by_stop
2. mart_crash_proximity_by_stop
3. mart_priority_hotspots
4. mart_reliability_by_route_day
5. mart_reliability_by_stop_hour
6. mart_vulnerability_by_stop
7. mart_weather_impacts

#### 6.2 DuckDB Mart Coverage

**Query**:
```sql
SELECT
  service_date_mst,
  COUNT(DISTINCT route_id) AS routes,
  COUNT(*) AS records
FROM mart_reliability_by_route_day
GROUP BY service_date_mst
ORDER BY service_date_mst DESC;
```

**What it shows**: Records per service date (helps identify gaps)

#### 6.3 Cross-Platform Consistency Check

**Queries**:
```sql
-- DuckDB mart stats
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM mart_reliability_by_route_day;
```

```sql
-- BigQuery mart stats
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS total_records
FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`;
```

**Success criteria**:
- ✅ PASS: Latest dates match + 0-5% record count difference
- ⚠️ WARN: 5-20% difference (acceptable for incremental marts)
- ⚠️ WARN: >20% difference or date mismatch (run `make sync-duckdb`)

**Why differences occur**:
- DuckDB syncs periodically, not real-time
- Incremental marts may have rolling windows
- BigQuery continues accumulating data after sync

**To refresh DuckDB**:
```bash
make sync-duckdb
```

---

## Expected Results by Stage

### Day 1 (First Day of Operation)

**Typical success rate**: **70-80%** (many expected warnings)

| Section | Expected Result | Notes |
|---------|-----------------|-------|
| **1. GitHub Actions** | ✅ 100% success | 2-5 hourly runs completed |
| **2. GCS Files** | ⚠️ 5-20 snapshots | Workflows started mid-day |
| **3.1 RT Freshness** | ✅ <120 min old | Latest snapshot recent |
| **3.2 Daily Coverage** | ⚠️ 120-239 snapshots | Accumulating throughout day |
| **3.3 Missing Hours** | ⚠️ Gaps outside launch window | Micro-batch flow only recently enabled |
| **3.4 Weather Freshness** | ✅ 1-7 days behind | NOAA lag is normal |
| **3.5 Weather Quality** | ✅ 70%+ complete | Historical data is good |
| **3.6 Precip Bins** | ⚠️ 1-2 bins | Limited recent data |
| **4. Staging** | ✅ Fresh | Views work correctly |
| **5.1 Reliability Mart** | ⚠️ 1-2 days | Just started collecting |
| **5.2 Weather Impacts** | ⚠️ 'none' only | Need 30+ days |
| **6. DuckDB** | ✅ Synced | If you ran `make sync-duckdb` |

**Key Day 1 warnings** (all normal):
- Missing hours (micro-batch enabled mid-day)
- Limited snapshots (first partial day)
- Only 1-2 days in marts (just started)
- Weather impacts showing 'none' only (need more days)

### Day 2 (First Full Day)

**Typical success rate**: **85-90%** (fewer warnings)

**Improvements**:
- ✅ ~288 snapshots/day
- ✅ Zero missing hours (24h coverage)
- ✅ ~600K trip updates/day
- ⚠️ Still only 2 days in marts (need 30+)

### After 30 Days (Steady State)

**Typical success rate**: **90-95%** (mostly passes)

**Full operation**:
- ✅ ~288 snapshots/day consistently
- ✅ 30+ days of transit data
- ✅ Weather impacts showing multiple precipitation bins
- ✅ Meaningful correlation analysis possible
- ⚠️ Only expected warnings: weather lag (3-7 days), DuckDB sync lag (periodic)

---

## Troubleshooting Guide

### Common Issues and Solutions

#### ❌ GitHub Actions Workflows Failing

**Symptoms**:
```
❌ FAIL: Realtime GTFS-RT: Only 3/10 runs succeeded (30%)
```

**Diagnosis**:
```bash
# View recent runs
gh run list --workflow=realtime-gtfs-rt.yml --limit 10

# View failed run logs
gh run view <run-id> --log
```

**Common causes**:
- API rate limits (RTD GTFS-RT API)
- GCS permissions issues
- Workflow syntax errors

**Solutions**:
- Check GitHub Actions logs for specific errors
- Verify GCS_BUCKET environment variable
- Verify service account permissions
- Check RTD GTFS-RT API status

#### ⚠️ Missing Hours (After Day 2)

**Symptoms**:
```
⚠️ WARN: Missing hours: 5, 6, 7 (3 missing hours)
```

**Diagnosis**:
```bash
# Check workflow schedule
cat .github/workflows/realtime-gtfs-rt.yml | grep schedule

# Check recent runs
gh run list --workflow=realtime-gtfs-rt.yml --limit 30
```

**Common causes**:
- Workflow disabled
- GitHub Actions concurrent limit hit
- Workflow schedule syntax error

**Solutions**:
- Verify workflow is enabled in GitHub Actions UI
- Check for workflow run queue backlog
- Verify cron schedule syntax

#### ❌ Weather Data >14 Days Behind

**Symptoms**:
```
❌ FAIL: Weather data freshness: 18 days behind
```

**Diagnosis**:
```bash
# Check last nightly ingest run
gh run list --workflow=nightly-ingest.yml --limit 5

# Check weather ingestion logs
gh run view <run-id> --log | grep -i weather
```

**Common causes**:
- NOAA API key expired/invalid
- NOAA API rate limiting
- Ingestion not run recently

**Solutions**:
- Verify NOAA_TOKEN environment variable
- Run manual re-ingestion: `python -m whylinedenver.ingest.weather --backfill-days 30`
- Check NOAA CDO API status

#### ⚠️ DuckDB Mart Date Mismatch

**Symptoms**:
```
⚠️ WARN: Mart sync: Date mismatch (BQ: 2025-10-23, DuckDB: 2025-10-20) - run 'make sync-duckdb'
```

**Solution**:
```bash
# Refresh DuckDB from BigQuery
make sync-duckdb

# Re-run QA to verify
./scripts/qa_script.sh
```

**Why it happens**: DuckDB syncs periodically, not real-time. This is expected and normal.

#### ❌ Low Weather Data Quality (<50%)

**Symptoms**:
```
❌ FAIL: Weather data quality: 42% complete
```

**Diagnosis**:
```sql
-- Check which columns are NULL
SELECT
  date,
  temp_max_c,
  temp_min_c,
  precip_mm,
  snow_mm,
  snowdepth_mm
FROM `whyline-denver.raw_denver.raw_weather_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY)
  AND date <= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 14 DAY)
  AND precip_mm IS NULL
ORDER BY date DESC
LIMIT 20;
```

**Common causes**:
- NOAA station data incomplete
- Wrong station ID
- API request parameters incorrect

**Solutions**:
- Verify NOAA station ID (USC00053005 for Denver)
- Check NOAA CDO API for station data availability
- Consider adding backup weather stations

#### ⚠️ Only 'none' Precipitation Bin

**Symptoms**:
```
⚠️ WARN: Weather impacts: Only 'none' bin (expected: need 30+ days + rainy days)
```

**Diagnosis**:
```sql
-- Check for rainy days
SELECT
  date,
  precip_mm,
  precip_bin
FROM `whyline-denver.stg_denver.stg_weather`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 90 DAY)
  AND precip_bin != 'none'
ORDER BY date DESC;
```

**Is this a problem?**
- ⚠️ **Day 1-7**: Normal (limited data)
- ⚠️ **Dry weather**: Normal (Denver has ~300 sunny days/year)
- ⚠️ **After 30+ days with no rain**: Unusual but possible

**Solutions**:
- Wait for rainy days to occur naturally
- Verify precipitation data is being captured correctly
- Check weather data collection includes rainy periods

---

## Query Reference

### Quick Manual Queries

If you want to run specific checks manually:

#### Check Today's Snapshot Count
```bash
bq query --nouse_legacy_sql "
SELECT
  DATE(feed_ts_utc, 'America/Denver') AS date,
  COUNT(DISTINCT feed_ts_utc) AS snapshots,
  COUNT(*) AS trip_updates
FROM \`whyline-denver.raw_denver.raw_gtfsrt_trip_updates\`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY date;
"
```

#### Check Weather Data Coverage (Last 30 Days)
```bash
bq query --nouse_legacy_sql "
SELECT
  COUNT(DISTINCT date) AS days_covered,
  COUNTIF(precip_mm IS NOT NULL) AS days_complete,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) AS pct_complete
FROM \`whyline-denver.raw_denver.raw_weather_daily\`
WHERE date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 30 DAY);
"
```

#### Check DuckDB Mart Freshness
```bash
duckdb data/warehouse.duckdb "
SELECT
  MAX(service_date_mst) AS latest_date,
  COUNT(DISTINCT service_date_mst) AS days,
  COUNT(*) AS records
FROM mart_reliability_by_route_day;
"
```

#### Check Workflow Success Rates
```bash
# Realtime GTFS-RT workflow
gh run list --workflow=realtime-gtfs-rt.yml --limit 10 --json conclusion | \
  jq '[.[] | .conclusion] | group_by(.) | map({status: .[0], count: length})'

# Realtime BQ load workflow
gh run list --workflow=realtime-bq-load.yml --limit 10 --json conclusion | \
  jq '[.[] | .conclusion] | group_by(.) | map({status: .[0], count: length})'
```

#### Check GCS Files
```bash
# Count today's GTFS-RT snapshots
TODAY_ISO=$(date -u +%Y-%m-%d)
gsutil ls "gs://whylinedenver-raw/raw/rtd_gtfsrt/" | grep "snapshot_at=${TODAY_ISO}" | wc -l

# List today's snapshots with timestamps
gsutil ls "gs://whylinedenver-raw/raw/rtd_gtfsrt/" | grep "snapshot_at=${TODAY_ISO}"

# Check weather file exists
gsutil ls "gs://whylinedenver-raw/raw/noaa_weather/date=$(date -u +%Y-%m-%d)/"
```

---

## Script Configuration

### Environment Variables

The script reads these environment variables (with defaults):

```bash
# Google Cloud Platform
PROJECT="${PROJECT:-whyline-denver}"
RAW_DATASET="${RAW_DATASET:-raw_denver}"
STG_DATASET="${STG_DATASET:-stg_denver}"
MART_DATASET="${MART_DATASET:-mart_denver}"

# Google Cloud Storage
GCS_BUCKET="${GCS_BUCKET:-whylinedenver-raw}"

# DuckDB
DUCKDB_PATH="${DUCKDB_PATH:-data/warehouse.duckdb}"

# Options
SKIP_DUCKDB="${SKIP_DUCKDB:-false}"
```

### Override Defaults

Create a `.env.qa` file:

```bash
# .env.qa
export PROJECT="my-custom-project"
export DUCKDB_PATH="/custom/path/to/warehouse.duckdb"
```

Then source it before running:

```bash
source .env.qa
./scripts/qa_script.sh
```

---

## Maintenance

### Keep Documentation Updated

Update this document when:
- Adding new validation checks
- Changing success criteria thresholds
- Adding new marts or tables
- Modifying workflow schedules

### Script Modification Guidelines

If you modify `scripts/qa_script.sh`:

1. **Maintain section structure** - Don't renumber sections
2. **Use consistent check functions** - `check_passed`, `check_warning`, `check_failed`
3. **Strip newlines from bash variables** - Use `tr -d '\n'` for counts
4. **Cast floats to integers** - BigQuery percentages need `CAST(ROUND(...) AS INT64)`
5. **Schema-qualify DuckDB tables** - Use `schema.table` format
6. **Update this documentation** - Keep query reference in sync

### Testing Changes

Before committing script changes:

```bash
# Test the script
./scripts/qa_script.sh

# Verify exit code
echo $?  # Should be 0 for success

# Check output formatting
./scripts/qa_script.sh | grep -E "(✅|⚠️|❌)"

# Verify all sections run
./scripts/qa_script.sh 2>&1 | grep "Section"
```

---

## Additional Resources

### Project Documentation
- **[Root README](../README.md)** – Project overview, quickstart, FAQ, medallion architecture, data lineage
- **[dbt Models Documentation](../dbt/models/README.md)** – All 29 models (staging, intermediate, marts), tests, materialization strategies
- **[GitHub Workflows Documentation](../.github/workflows/README.md)** – How the 6 automated workflows orchestrate ingestion, transformation, and sync
- **[Pipeline Architecture](ARCHITECTURE.md)** – Deep dive into data flow, medallion layers, design decisions, and adaptation guide
- **[Data Contracts](contracts/CONTRACTS.md)** – Schema specifications for all CSV outputs; breaking change policy

### External Resources
- [RTD GTFS-RT API](https://www.rtd-denver.com/developer-resources/gtfs-realtime)
- [NOAA Climate Data Online API](https://www.ncdc.noaa.gov/cdo-web/webservices/v2)
- [BigQuery Documentation](https://cloud.google.com/bigquery/docs)
- [DuckDB Documentation](https://duckdb.org/docs/)

---

## Summary

The QA validation script is your **single source of truth** for pipeline health:

- ✅ **Run it often** - After deploys, during troubleshooting, or for routine monitoring
- ✅ **Trust the warnings** - Day 1 warnings are expected and documented
- ✅ **Act on failures** - Check GitHub Actions logs, verify permissions, re-run ingestion
- ✅ **Sync DuckDB regularly** - Use `make sync-duckdb` to keep local database fresh
- ✅ **Wait for accumulation** - Weather impact analysis needs 30+ days of data

**Current system health metrics**:
- **Day 1**: 70-80% success rate (expected)
- **Day 2**: 85-90% success rate (normal)
- **Steady state (30+ days)**: 90-95% success rate (excellent)

If you see consistent failures or success rate <70%, investigate using the troubleshooting guide above.

---

**Questions or issues?** Check GitHub Actions logs, BigQuery tables, and GCS bucket contents. The script provides detailed output to help pinpoint problems.
