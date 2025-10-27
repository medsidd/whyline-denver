# NOAA Weather Data Collection Strategy

Weather data is essential for analyzing transit reliability impacts, but NOAA's Climate Data Online (CDO) API publishes incomplete data that gets finalized over the following 3-14 days. This document explains our rolling window re-ingestion strategy to handle late-arriving data.

## The NOAA Data Lag Problem

NOAA publishes daily weather observations through their CDO API, but recent data is often incomplete at first publication.

**Typical timeline for a given date:**
- Day 0: Event occurs (e.g., October 10th)
- Day 1: API returns: `precip=NULL, tmin=NULL, tmax=NULL`
- Day 3: Same request returns: `precip=5mm, tmin=NULL, tmax=NULL`
- Day 8: Complete data: `precip=5mm, tmin=8°C, tmax=18°C`

Weather stations report data in batches, and NOAA's quality control process takes 3-14 days depending on the metric.

**This creates a design challenge:**
- Single ingestion: Misses late-arriving data
- Daily re-ingestion: Requires duplicate handling and versioning

We implemented a rolling window re-ingestion pattern with a two-layer deduplication strategy.

## Two-Layer Architecture

### Layer 1: Raw Table (Append-Only)

`raw_weather_daily` uses an append-only pattern. Each nightly ingestion writes new rows—even for dates already in the table.

This means a single date (e.g., October 10th) may appear 30+ times with different `_ingested_at` timestamps. Some rows have NULLs, later rows have complete data.

**Rationale for append-only:**
- BigQuery charges per data scanned, not stored. Appending ~1KB/day costs negligible amounts.
- Preserves data lineage. We can query historical versions: "What did the data look like on October 15th?"
- Appends are idempotent. No risk of update conflicts or schema lock issues.

### Layer 2: Staging View (Latest Version)

`stg_weather` deduplicates using a window function:

```sql
SELECT
  *,
  row_number() over (partition by date, station order by _ingested_at desc) as record_rank
FROM raw_weather_daily
WHERE record_rank = 1
```

This returns the most recently ingested row for each (date, station) combination. If the latest ingestion has NULLs, we serve NULLs—indicating "data not yet finalized" rather than serving stale data.

## Nightly Rolling 30-Day Re-Ingest

The `nightly-ingest.yml` workflow runs daily at 8am UTC (1-2am MST):

```bash
python -m whylinedenver.ingest.noaa_daily \
  --start $(date -u -v-30d +%Y-%m-%d) \
  --end $(date -u -v-1d +%Y-%m-%d) \
  --gcs --bucket whylinedenver-raw
```

**Process:**
1. Fetch weather data for the last 30 days
2. Write CSV to GCS at `raw/noaa_daily/extract_date=YYYY-MM-DD/`
3. `bq-load` workflow appends to BigQuery

**Why 30 days?**
- NOAA finalization lag is 3-14 days depending on metric
- Re-ingesting 30-day window captures all late-arriving data
- Earlier dates are already finalized, so re-ingesting them is redundant but harmless

**Cost:** ~30 seconds compute, <$0.10/year storage.

## Data Quality Expectations

Weather completeness depends on recency:

| Days Ago | Expected Completeness | Status |
|----------|----------------------|--------|
| 0-3 | 0-20% | Not yet finalized |
| 4-7 | 40-80% | Partial finalization (precipitation usually first) |
| 8-14 | 80-95% | Mostly complete |
| 15+ | 95-100% | Fully finalized |

**Historical data (2024):**
- Temperature: 98-100% complete
- Precipitation: 95-100% complete
- Snow: 95-100% complete (seasonal)

Querying recent dates will show NULLs. This is expected behavior.

## Initial Historical Data Collection

A one-time historical collection ran for January 1, 2024 through September 30, 2025 (21 months of historical data).

Script (`scripts/collect_noaa_2024.sh`):
```bash
for month in {1..9}; do
  python -m whylinedenver.ingest.noaa_daily \
    --start 2024-${month}-01 \
    --end 2024-${month}-31 \
    --gcs --bucket whylinedenver-raw
  sleep 5  # Rate limiting
done
```

Execution time: ~10 minutes. Required only once.

## Validation Queries

**Check completeness by month:**
```sql
SELECT
  DATE_TRUNC(date, MONTH) as month,
  COUNT(*) as total_days,
  COUNTIF(precip_mm IS NOT NULL) as days_with_precip,
  COUNTIF(tmin_c IS NOT NULL) as days_with_temp,
  ROUND(COUNTIF(precip_mm IS NOT NULL) / COUNT(*) * 100, 1) as precip_pct
FROM `whyline-denver.stg_denver.stg_weather`
WHERE date >= '2024-01-01'
GROUP BY month
ORDER BY month DESC;
```

Run monthly. If historical months show <90% completeness, re-run ingestion for that period.

**Recent updates:**
```sql
SELECT
  date,
  MAX(_ingested_at) as latest_ingest,
  DATE_DIFF(CURRENT_DATE(), date, DAY) as days_ago,
  COUNTIF(precip_mm IS NOT NULL) as has_precip
FROM `whyline-denver.raw_denver.raw_weather_daily`
WHERE _ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY date
ORDER BY date DESC;
```

Shows which dates received new data in the last week. Useful for verifying the nightly rolling window re-ingestion.

**Verify deduplication (should return 0 rows):**
```sql
SELECT date, COUNT(*) as cnt
FROM `whyline-denver.stg_denver.stg_weather`
GROUP BY date
HAVING COUNT(*) > 1;
```

If this returns rows, the staging deduplication logic is broken.

## Troubleshooting

**Recent data has many NULLs:**

Expected for dates within the last 7 days. Data from the last week is typically 60-100% NULL pending finalization.

**Historical data has unexpected NULLs:**

Re-run data collection for that date range:
```bash
python -m whylinedenver.ingest.noaa_daily \
  --start 2024-06-01 --end 2024-06-30 \
  --gcs --bucket whylinedenver-raw
```

If NULLs persist, NOAA may not have data for those dates (rare but possible).

**Staging shows NULL but raw table has data:**

Check if the newer ingestion actually contains complete data. The staging layer always serves the latest `_ingested_at` row, even if it's NULL. This is correct behavior—serving NULL is more accurate than serving potentially stale data.

**NOAA API returns empty responses:**

Common causes:
1. Requesting data <7 days old (wait for finalization)
2. Incorrect station ID (should be `USW00023062` for Denver International Airport)
3. Expired API token (request new token at https://www.ncdc.noaa.gov/cdo-web/token)
4. NOAA service outage (rare)

## Cost Analysis

**Storage:**
- Raw table: ~1KB/day × 730 days = ~730KB
- GCS files: ~5KB each (gzipped CSV)
- **Total: <$0.01/month**

**Compute:**
- Nightly re-ingestion: ~30KB/day
- Annual: ~10MB
- **Cost: <$0.10/year**

BigQuery partitions by `DATE(_extract_date)`, so queries only scan relevant partitions. A typical 30-day query scans ~300KB.

## Maintenance Schedule

**Daily (automated):**
- 8am UTC: Ingest last 30 days via GitHub Actions
- Duration: ~30 seconds
- No action required unless workflow fails

**Weekly (manual check):**
- Run completeness query
- Identify persistent gaps

**Monthly (recommended):**
- Review data quality for previous month
- Re-run ingestion if necessary

**Quarterly (optional):**
- Re-run ingestion for recent quarters to capture final corrections
- Example: January 2026, re-ingest Q4 2025

## Success Criteria

Weather pipeline is considered healthy when:
- 95%+ of dates >14 days old have complete data
- Nightly ingestion maintains 100% success rate
- No manual interventions required (except monthly spot checks)

The 30-day rolling window strategy has maintained these criteria consistently since deployment.

---

## Additional Resources

- **[Root README](../../README.md)** – Project overview and quickstart
- **[Pipeline Architecture](../ARCHITECTURE.md)** – How weather data integrates with overall pipeline
- **[dbt Models Documentation](../../dbt/models/README.md)** – How `stg_weather` feeds reliability marts
- **[GitHub Workflows Documentation](../../.github/workflows/README.md)** – Nightly weather ingestion workflow details
- **[QA Validation Guide](../QA_Validation_Guide.md)** – Weather freshness and quality validation procedures
- **[Data Contracts](../contracts/CONTRACTS.md)** – Weather CSV schema specification

## External References

- [NOAA CDO API Documentation](https://www.ncdc.noaa.gov/cdo-web/webservices/v2)
- [Denver International Airport Station](https://www.ncdc.noaa.gov/) — Station ID: USW00023062
- [Request API Token](https://www.ncdc.noaa.gov/cdo-web/token) — Free, rate-limited to 1000 requests/day
