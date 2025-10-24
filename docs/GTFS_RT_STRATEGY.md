# GTFS Realtime Snapshot Strategy

## Overview

This document explains our hourly GTFS-RT snapshot approach for capturing comprehensive transit reliability data throughout RTD's operating hours.

---

## 📊 Data Collection Architecture

### Snapshot Schedule

**Frequency:** Every hour from 5am - 7pm MST (15 hours/day)
**Per-hour capture:** 3 snapshots, 2 minutes apart
**Daily total:** 45 snapshots/day
**Annual volume:** ~16,425 snapshots/year

### Coverage Windows

| Time Period | Hours (MST) | Purpose | Priority |
|-------------|-------------|---------|----------|
| **Early Morning** | 5-6am | Pre-rush baseline | Medium |
| **Morning Rush** | 7-9am | Peak delays, weather impact | **HIGH** |
| **Midday** | 10am-3pm | Normal operations | Medium |
| **Evening Rush** | 4-7pm | Peak delays, weather impact | **HIGH** |

---

## 🔄 Workflow Architecture

### 1. Hourly Snapshot Capture
**File:** [.github/workflows/hourly-gtfs-rt.yml](../.github/workflows/hourly-gtfs-rt.yml)

**Schedule:** Runs at the top of each hour (12pm-2am UTC)
```yaml
- cron: "0 14 * * *"  # 7am MST - Morning rush
- cron: "0 15 * * *"  # 8am MST - Peak morning
- cron: "0 23 * * *"  # 4pm MST - Evening rush start
# ... (15 times per day)
```

**What it does:**
1. Fetches RTD's GTFS-RT trip_updates feed
2. Fetches RTD's GTFS-RT vehicle_positions feed
3. Captures 3 snapshots 2 minutes apart
4. Uploads to GCS: `gs://bucket/raw/rtd_gtfsrt/snapshot_at=YYYY-MM-DDTHH:MM/`

**Output per run:**
- `trip_updates.csv.gz` (~500KB, 5,000-10,000 updates)
- `vehicle_positions.csv.gz` (~50KB, 400-500 positions)

---

### 2. Hourly BigQuery Load
**File:** [.github/workflows/hourly-bq-load.yml](../.github/workflows/hourly-bq-load.yml)

**Schedule:** Runs 30 minutes after snapshots (gives buffer time)
```yaml
- cron: "30 14 * * *"  # 7:30am MST - Load 7am data
- cron: "30 15 * * *"  # 8:30am MST - Load 8am data
# ... (15 times per day)
```

**What it does:**
1. Scans GCS for new GTFS-RT files
2. Loads to `raw_gtfsrt_trip_updates` table
3. Loads to `raw_gtfsrt_vehicle_positions` table
4. Tracks loaded files to avoid duplicates

---

### 3. Nightly Static Data Ingest
**File:** [.github/workflows/nightly-ingest.yml](../.github/workflows/nightly-ingest.yml)

**Schedule:** Once per day at 8am UTC (1-2am MST)

**What it does:**
1. GTFS static schedule (routes, stops, trips, etc.)
2. NOAA weather data (30-day rolling window)
3. Denver crashes data
4. Denver sidewalks data
5. ACS demographic data
6. Census tracts

**Note:** Does NOT capture GTFS-RT (handled by hourly workflow)

---

### 4. Nightly Marts Build
**File:** [.github/workflows/nightly-bq.yml](../.github/workflows/nightly-bq.yml)

**Schedule:** 9am UTC (2-3am MST) - after nightly ingest

**What it does:**
1. Builds staging layer (dedups, cleans)
2. Builds intermediate models
3. Builds mart tables (reliability, weather impacts, etc.)
4. Runs dbt tests
5. Exports marts to GCS as parquet

---

## 💰 Cost Analysis

### Storage Costs

| Component | Size | Annual Volume | Cost |
|-----------|------|---------------|------|
| **GTFS-RT snapshots** | ~550KB/snapshot | ~9GB/year | ~$0.20/year |
| **BigQuery raw table** | Compressed | ~15GB/year | ~$0.30/year |
| **Marts (exported)** | Parquet | ~2GB/year | ~$0.05/year |
| **Total Storage** | | | **~$0.55/year** |

### Compute Costs

| Workflow | Runs/Day | Duration | Cost/Run | Daily Cost |
|----------|----------|----------|----------|------------|
| **Hourly snapshots** | 15 | ~30 sec | $0.003 | $0.045 |
| **Hourly BQ load** | 15 | ~20 sec | $0.002 | $0.030 |
| **Nightly static** | 1 | ~2 min | $0.010 | $0.010 |
| **Nightly marts** | 1 | ~5 min | $0.020 | $0.020 |
| **Total Compute** | | | | **~$0.105/day** |

**Monthly Cost:** ~$3.15/month
**Annual Cost:** ~$38/year

**Cost per snapshot:** $0.003
**Cost per data point:** ~$0.0001

---

## 📈 Data Volume Projections

### Daily Accumulation

```
Snapshots/day:        45
Updates/snapshot:     ~8,000 (trip updates)
Positions/snapshot:   ~450 (vehicle positions)

Daily trip updates:   ~360,000 rows
Daily positions:      ~20,250 rows
Daily total:          ~380,000 rows
```

### Monthly & Annual

```
Monthly:   ~11.4 million trip updates
           ~607,500 vehicle positions
           ~12 million rows total

Annual:    ~137 million trip updates
           ~7.3 million vehicle positions
           ~144 million rows total
```

### BigQuery Table Sizes (Compressed)

- **raw_gtfsrt_trip_updates:** ~1.3GB/month, ~15GB/year
- **raw_gtfsrt_vehicle_positions:** ~70MB/month, ~840MB/year
- **Total:** ~16GB/year (compressed, partitioned)

---

## 🎯 Data Quality Benefits

### What This Enables

1. **Peak Hour Analysis**
   - Morning rush reliability (7-9am)
   - Evening rush reliability (4-7pm)
   - Hour-by-hour delay patterns

2. **Weather Impact Correlation**
   - Real weather conditions during actual delays
   - Rush hour weather impacts (most critical)
   - Precipitation timing effects

3. **Route Performance**
   - Identify consistently late routes
   - Bunching patterns
   - Headway adherence by time of day

4. **Stop-Level Metrics**
   - On-time performance by stop
   - Hourly reliability scores
   - Problem areas during specific hours

---

## 🔍 Monitoring & Validation

### Daily Health Checks

```sql
-- Verify hourly snapshots are captured
SELECT
  DATE(feed_ts_utc, 'America/Denver') as snapshot_date,
  EXTRACT(HOUR FROM TIMESTAMP(feed_ts_utc, 'America/Denver')) as hour_mst,
  COUNT(DISTINCT feed_ts_utc) as num_snapshots,
  COUNT(*) as num_updates
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY snapshot_date, hour_mst
ORDER BY hour_mst;
```

**Expected:** 3 snapshots for each hour from 5am-7pm MST

### Weekly Coverage Report

```sql
-- Check weekly coverage and gaps
WITH hourly_coverage AS (
  SELECT
    DATE(feed_ts_utc, 'America/Denver') as date,
    EXTRACT(HOUR FROM TIMESTAMP(feed_ts_utc, 'America/Denver')) as hour,
    COUNT(DISTINCT feed_ts_utc) as snapshots
  FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
  WHERE DATE(feed_ts_utc, 'America/Denver') >= CURRENT_DATE('America/Denver') - 7
  GROUP BY date, hour
)

SELECT
  date,
  COUNT(*) as hours_with_data,
  SUM(snapshots) as total_snapshots,
  COUNTIF(snapshots >= 3) as hours_complete,
  COUNTIF(snapshots < 3) as hours_incomplete,
  ROUND(COUNTIF(snapshots >= 3) / COUNT(*) * 100, 1) as pct_complete
FROM hourly_coverage
GROUP BY date
ORDER BY date DESC;
```

**Target:** >90% complete hours (some outages acceptable)

---

## 🚨 Troubleshooting

### Issue: Missing Snapshots

**Check workflow runs:**
```bash
# View recent hourly-gtfs-rt runs
gh run list --workflow=hourly-gtfs-rt.yml --limit 20
```

**Common causes:**
1. GitHub Actions quota exceeded (free tier: 2,000 min/month)
2. RTD API temporarily down
3. GCS bucket write permissions issue

**Solution:** Check logs, verify credentials, monitor RTD API status

---

### Issue: Snapshots Not Loading to BigQuery

**Check load workflow:**
```bash
# View recent hourly-bq-load runs
gh run list --workflow=hourly-bq-load.yml --limit 20
```

**Common causes:**
1. bq-load running before snapshot upload completes
2. BigQuery table schema mismatch
3. GCS permissions issue

**Solution:** Verify 30-minute buffer is sufficient, check BQ table schema

---

### Issue: High Costs

**Check actual usage:**
```sql
-- Calculate actual data volume
SELECT
  DATE(_ingested_at) as date,
  COUNT(*) as rows,
  ROUND(SUM(LENGTH(TO_JSON_STRING(t))) / 1024 / 1024, 2) as mb
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates` t
WHERE DATE(_ingested_at) >= CURRENT_DATE() - 30
GROUP BY date
ORDER BY date DESC;
```

**If costs exceed projections:**
1. Reduce snapshot frequency (every 2 hours instead of hourly)
2. Reduce snapshots per run (2 instead of 3)
3. Limit to peak hours only (7-9am, 4-7pm)

---

## 🔄 Alternative Schedules

### Peak Hours Only (Lower Cost)

**6 runs/day instead of 15:**
```yaml
schedule:
  - cron: "0 14 * * *"  # 7am MST
  - cron: "0 15 * * *"  # 8am MST
  - cron: "0 16 * * *"  # 9am MST
  - cron: "0 23 * * *"  # 4pm MST
  - cron: "0 0 * * *"   # 5pm MST
  - cron: "0 1 * * *"   # 6pm MST
```

**Cost:** ~$1.20/month (60% reduction)
**Coverage:** Rush hours only (still captures 80% of delays)

### Every 2 Hours (Moderate)

**8 runs/day instead of 15:**
```yaml
schedule:
  - cron: "0 12 * * *"  # 5am MST
  - cron: "0 14 * * *"  # 7am MST
  - cron: "0 16 * * *"  # 9am MST
  - cron: "0 18 * * *"  # 11am MST
  - cron: "0 20 * * *"  # 1pm MST
  - cron: "0 22 * * *"  # 3pm MST
  - cron: "0 0 * * *"   # 5pm MST
  - cron: "0 2 * * *"   # 7pm MST
```

**Cost:** ~$1.60/month (50% reduction)
**Coverage:** Good throughout day

---

## 📚 References

- RTD GTFS-RT Feed: https://www.rtd-denver.com/developers/gtfs-rt
- GTFS-RT Specification: https://gtfs.org/realtime/
- GitHub Actions Pricing: https://docs.github.com/en/billing/managing-billing-for-github-actions
- BigQuery Pricing: https://cloud.google.com/bigquery/pricing
