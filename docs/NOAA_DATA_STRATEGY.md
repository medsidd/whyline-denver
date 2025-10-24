# NOAA Weather Data Strategy

## Overview

This document explains our approach to ingesting and maintaining NOAA weather data with automatic deduplication and efficient updates.

---

## 📊 Data Architecture

### Raw Layer (`raw_weather_daily`)
- **Purpose:** Append-only storage of all ingestion runs
- **Behavior:** Multiple ingests of the same date create multiple rows
- **Cost:** Low (compressed, partitioned by date)

### Staging Layer (`stg_weather`)
- **Purpose:** Deduplicates raw data, always serving latest ingestion
- **Logic:** `row_number() over (partition by date, station order by _ingested_at desc)`
- **Result:** Single row per (date, station), picking most recent data

---

## 🔄 Ingestion Strategy

### Phase 1: Historical Backfill (ONE-TIME)

**Date Range:** January 1, 2024 → September 30, 2025

**Why these dates?**
- 2024 data is fully finalized and complete
- Early 2025 data should be mostly complete
- Provides ~21 months of historical weather context

**Execution:**
```bash
export NOAA_CDO_TOKEN="your-token"
export GCS_BUCKET="your-bucket"
./scripts/backfill_noaa_2024.sh
```

**Expected Quality:**
- 2024: 95-100% complete (all weather metrics)
- Q1-Q3 2025: 80-95% complete (some recent gaps)

---

### Phase 2: Daily Rolling Updates (ONGOING)

**Date Range:** Last 30 days (ending yesterday)

**Makefile Configuration:**
```makefile
ingest-noaa:
	@set -euo pipefail; \
	START_DATE=$$(date -u -v-30d +%Y-%m-%d 2>/dev/null || date -u -d '30 days ago' +%Y-%m-%d); \
	END_DATE=$$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d); \
	$(PY) -m whylinedenver.ingest.noaa_daily $(INGEST_MODE_ARGS) --start $$START_DATE --end $$END_DATE
```

**How it works:**
1. Every night at 8am UTC (nightly-ingest workflow)
2. Fetch last 30 days of weather data
3. Upload to GCS (overwrites same extract_date if re-run same day)
4. Load to BigQuery (appends new rows)
5. Staging layer automatically picks latest `_ingested_at`

**Why 30 days?**
- NOAA data has 3-7 day finalization lag
- 30-day window ensures we capture updates to incomplete records
- Example: Oct 10 might have NULL on Oct 11, but complete data on Oct 18

---

## 💰 Cost Efficiency

### Storage Costs (Minimal)
- **Raw table:** ~1KB per day = ~365KB per year
- **GCS:** ~5KB per file (gzipped CSV)
- **Total for 2 years:** < $0.01/month

### Query Costs (Optimized)
- Staging view uses `where record_rank = 1` after window function
- BigQuery only scans partitions needed
- Typical mart query: ~10KB scanned per date partition

### Update Strategy Costs
- **Daily re-ingest of 30 days:** ~30KB new data/day
- **Monthly accumulation:** ~900KB raw data
- **Annual accumulation:** ~10MB raw data
- **Cost impact:** Negligible (<$0.10/year)

---

## 📈 Data Quality Expectations

### Historical Data (2024)
| Metric | Expected Coverage | Notes |
|--------|------------------|-------|
| Temperature (TMIN, TMAX) | 98-100% | Core measurements, rarely missing |
| Precipitation (PRCP) | 95-100% | Occasional sensor issues |
| Snow (SNOW) | 95-100% | Only relevant in winter |
| Derived (TAVG, bins) | 98-100% | Calculated from above |

### Recent Data (Last 30 days)
| Days Ago | Expected Coverage | Notes |
|----------|------------------|-------|
| 0-3 days | 0-20% | Data not finalized yet |
| 4-7 days | 40-80% | Partial finalization |
| 8-14 days | 80-95% | Mostly complete |
| 15-30 days | 95-100% | Fully finalized |

---

## 🔍 Validation Queries

### Check Data Completeness
```sql
SELECT
  DATE_TRUNC(date, MONTH) as month,
  COUNT(*) as days,
  COUNTIF(precip_mm IS NOT NULL) as days_with_precip,
  COUNTIF(tmin_c IS NOT NULL) as days_with_temp,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) as precip_coverage_pct,
  ROUND(COUNTIF(tmin_c IS NOT NULL) / COUNT(*) * 100, 1) as temp_coverage_pct
FROM `whyline-denver.stg_denver.stg_weather`
WHERE date >= '2024-01-01'
GROUP BY month
ORDER BY month DESC;
```

### Check Recent Updates
```sql
-- See which dates were updated in the last 7 days
SELECT
  DATE(date) as weather_date,
  MAX(_ingested_at) as latest_ingest,
  DATE_DIFF(CURRENT_DATE(), DATE(date), DAY) as days_ago,
  COUNTIF(precip_mm IS NOT NULL) as has_precip,
  COUNTIF(tmin_c IS NOT NULL) as has_temp
FROM `whyline-denver.raw_denver.raw_weather_daily`
WHERE _ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY weather_date
ORDER BY weather_date DESC;
```

### Find Duplicates in Raw (Expected)
```sql
-- This should show duplicates (normal behavior)
SELECT
  date,
  station,
  COUNT(*) as num_ingestions,
  STRING_AGG(CAST(DATE(_ingested_at) AS STRING) ORDER BY _ingested_at) as ingest_dates
FROM `whyline-denver.raw_denver.raw_weather_daily`
WHERE date >= '2025-10-01'
GROUP BY date, station
HAVING COUNT(*) > 1
ORDER BY num_ingestions DESC;
```

### Verify Staging Deduplication (No Duplicates)
```sql
-- This should return 0 rows (no duplicates)
SELECT
  date,
  station,
  COUNT(*) as cnt
FROM `whyline-denver.stg_denver.stg_weather`
GROUP BY date, station
HAVING COUNT(*) > 1;
```

---

## 🚨 Troubleshooting

### Issue: High NULL rates in recent data
**Expected:** Last 7 days will have 60-100% NULL rates
**Action:** Wait 7 days and re-check same dates

### Issue: Historical data has NULLs
**Problem:** Backfill didn't complete or API returned empty
**Action:** Re-run backfill for specific date range:
```bash
PYTHONPATH=$PWD/src python -m whylinedenver.ingest.noaa_daily \
  --gcs --bucket $GCS_BUCKET \
  --start 2024-06-01 --end 2024-06-30
```

### Issue: Staging still shows old values
**Problem:** Newer ingestion had NULL, older had data
**Behavior:** Deduplication picks latest `_ingested_at`, even if NULL
**Solution:** This is correct! NULL means "no data reported yet", which is more recent info than old data

### Issue: NOAA API returns empty
**Common causes:**
1. Recent dates (< 7 days old) - Wait for finalization
2. Future dates - Check Makefile isn't requesting future
3. Invalid station ID - Verify USW00023062 (Denver airport)
4. Token expired - Request new token

---

## 📅 Maintenance Schedule

### Daily (Automated via GitHub Actions)
- **Time:** 8:00 AM UTC (1-2 AM MST)
- **Action:** Ingest last 30 days
- **Duration:** ~30 seconds
- **Cost:** ~$0.001

### Weekly (Manual Check)
- **Action:** Run validation queries
- **Check:** Data completeness for last 30 days

### Monthly (Manual Review)
- **Action:** Review missing rates in manifest
- **Check:** Identify any persistent gaps

### Quarterly (Optional Backfill)
- **Action:** Re-backfill recent quarters to fill gaps
- **Example:** In Jan 2026, re-run Q4 2025 to get final data

---

## 🎯 Success Metrics

### Data Availability
- ✅ Target: 95%+ coverage for dates > 14 days old
- ✅ Target: 80%+ coverage for dates 7-14 days old
- ⚠️ Expected: <50% coverage for dates < 7 days old

### Pipeline Reliability
- ✅ Target: 100% successful nightly ingests
- ✅ Target: <5 minute ingestion time
- ✅ Target: Zero manual interventions per month

### Cost Efficiency
- ✅ Target: <$1/month storage + compute
- ✅ Target: <10MB monthly data growth
- ✅ Target: <100KB per staging query

---

## 📚 References

- NOAA CDO API: https://www.ncdc.noaa.gov/cdo-web/webservices/v2
- Station USW00023062: Denver International Airport
- Data Dictionary: https://www.ncei.noaa.gov/pub/data/cdo/documentation/
- Token Request: https://www.ncdc.noaa.gov/cdo-web/token
