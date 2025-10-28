# GTFS Realtime Snapshot Strategy

We capture RTD's realtime transit data every hour from 5am to 7pm MST, resulting in 45 snapshots per day. This document explains the rationale for high-frequency sampling and how the hourly workflows orchestrate data collection.

## What We're Capturing

RTD publishes two GTFS Realtime feeds that update approximately every minute:

**Trip Updates** — Delay information at stop level
- For every active trip at every stop: seconds ahead or behind schedule
- Primary data source for reliability analysis

**Vehicle Positions** — Real-time GPS locations
- Coordinates, heading, speed, and route assignment for every vehicle
- Used for visualizations and coverage analysis

Both feeds use Protocol Buffer format, which we immediately convert to CSV for compatibility with SQL-based transformations.

## The 45-Snapshots-Per-Day Strategy

A single daily snapshot would provide limited analytical value. Consider: "Route 15 had a 12-minute delay at 8:03am" tells us nothing about whether that delay lasted 2 minutes or 2 hours, or whether it was isolated or systemic.

**Benefits of dense temporal sampling:**

With 45 snapshots across 15 hours, we can:
- Distinguish chronic delays (appearing in consecutive snapshots) from transient ones
- Track delay propagation across routes and time periods
- Identify whether delays compound during rush hours or remain constant
- Measure delay resolution times

**Cost-benefit analysis:**

Annual infrastructure cost is ~$8/year for the entire GTFS-RT pipeline (storage + compute). The data richness gained from 45 snapshots versus 5 snapshots far outweighs the marginal cost increase.

## Coverage Schedule

Snapshots run **every hour from 5am to 7pm MST** (15 hours).

| Time Block | Rationale |
|------------|-----------|
| **5-6am** | Service initialization, establishes daily baseline |
| **7-9am** | Morning rush, peak delay period, weather impacts most visible |
| **10am-3pm** | Midday operations, useful for headway analysis |
| **4-7pm** | Evening rush, second peak delay period |
| **8pm-4am** | Skipped. RTD runs minimal service; cost exceeds value |

## Workflow Architecture

Two GitHub Actions workflows run in sequence:

### Workflow 1: Snapshot Capture (`realtime-gtfs-rt.yml`)

Runs 15 times per day at the top of each hour (5am, 6am, ..., 7pm MST).

**Execution:**
1. Minute 0: Fetch Trip Updates and Vehicle Positions, write to GCS
2. Minute 2: Second snapshot
3. Minute 4: Third snapshot

**Why three snapshots per run?**
- Redundancy: RTD's API occasionally returns 503 errors or empty responses
- Smoothing: Captures API jitter and transient anomalies

**Output**: ~550KB per run (500KB trip updates, 50KB vehicle positions)
**Duration**: ~3 minutes

### Workflow 2: BigQuery Load (`realtime-bq-load.yml`)

Runs 30 minutes after each snapshot (e.g., 5:30am, 6:30am, etc.).

**Why the delay?**
The snapshot workflow needs time to upload files to GCS. A 30-minute buffer ensures files are available before the load job scans GCS.

**Execution:**
1. Scan GCS for new files since last run
2. Load CSVs into `raw_gtfsrt_trip_updates` and `raw_gtfsrt_vehicle_positions`
3. Record MD5 hash in `__ingestion_log` to prevent duplicate loads

**Duration**: ~2 minutes

## Data Volume & Costs

**Daily:**
- 15 hourly runs × 3 snapshots = 45 snapshots
- ~25MB compressed
- ~360,000 trip update rows
- ~18,000 vehicle position rows

**Annual:**
- 16,425 snapshots
- ~9GB compressed
- ~144 million trip update rows
- ~7 million vehicle position rows

**Infrastructure costs:**
- GCS storage: $0.55/year
- BigQuery storage: $0.40/year
- BigQuery compute (dbt runs): ~$7/year
- GitHub Actions: $0 (800 min/month out of 2,000 free)

**Total: ~$8/year**

For comparison, an equivalent pipeline on a t3.small EC2 instance would cost $100-200/year.

## Analytical Use Cases

Dense temporal data enables several types of analysis:

**Reliability metrics:**
- Chronic vs. transient delays by route
- Seasonal reliability patterns
- Cross-route comparisons

**Temporal patterns:**
- Rush hour vs. midday reliability differences
- Time-of-day variability metrics

**Weather impact analysis:**
- Precipitation effects on bus delays (requires joining with weather data)
- Snow impact on light rail punctuality

**Equity analysis:**
- Reliability by service area demographics (requires Census tract joins)

All of these analyses require multiple measurements per day. Sparse sampling would miss critical temporal dynamics.

## Data Quality Expectations

Not all scheduled trips appear in every snapshot. Typical coverage:

**High coverage (90-100% of scheduled trips):**
- Bus routes during rush hours
- All light rail lines (A, B, C, D, E, F, G, H, W)

**Moderate coverage (60-90%):**
- Bus routes during midday
- Express routes (infrequent service)

**Low coverage (<60%):**
- Routes with few trips per hour
- Early morning / late evening service

**Known data quirks:**
- Occasional extreme delay values (>2 hours) are data errors. We flag delays outside [-3600, 7200] seconds but still load them for staging layer filtering.
- Some trips lack corresponding vehicle positions due to disabled GPS or API sync lag.
- Vehicle positions filtered to lon ∈ [-105.5, -104.4], lat ∈ [39.4, 40.2] to exclude GPS errors.

## Validation Queries

**Check today's snapshot coverage:**
```sql
SELECT
  COUNT(DISTINCT feed_ts_utc) as num_snapshots,
  COUNT(*) as trip_updates
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver');
```
Expected: ~45 snapshots, ~360K trip updates

**Find missing hours:**
```sql
WITH hours AS (
  SELECT hour FROM UNNEST(GENERATE_ARRAY(5, 19)) AS hour
),
captured AS (
  SELECT DISTINCT EXTRACT(HOUR FROM DATETIME(feed_ts_utc, 'America/Denver')) AS hour
  FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
  WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
)
SELECT h.hour
FROM hours h
LEFT JOIN captured c ON h.hour = c.hour
WHERE c.hour IS NULL;
```
Any results indicate missing snapshots; check GitHub Actions for failures.

**Delay distribution:**
```sql
SELECT
  CASE
    WHEN arrival_delay_sec < -300 THEN 'Early >5min'
    WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 'On Time'
    WHEN arrival_delay_sec BETWEEN 300 AND 900 THEN 'Late 5-15min'
    ELSE 'Very Late >15min'
  END AS delay_bucket,
  COUNT(*) as count,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER() * 100, 1) as pct
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY delay_bucket;
```
Expected distribution: 70-80% "On Time", 10-15% "Late 5-15min", remainder distributed.

## Troubleshooting

**Fewer than 18 snapshots captured:**

Check workflow runs:
```bash
gh run list --workflow=realtime-gtfs-rt.yml --limit 20
```

Common causes:
- GitHub Actions cron jitter (5-15 minute delays during peak times)
- RTD API downtime
- Workflow disabled

One-day gaps are acceptable; investigate if pattern persists for 3+ days.

**Duplicate snapshots in BigQuery:**

MD5 deduplication should prevent this. If duplicates appear:
```sql
SELECT
  feed_ts_utc,
  COUNT(*) as dupe_count
FROM `whyline-denver.raw_denver.raw_gtfsrt_trip_updates`
WHERE DATE(feed_ts_utc, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY feed_ts_utc
HAVING COUNT(*) > 10000;
```

Check `__ingestion_log` for errors. Manual deduplication may be required.

## Alternative Schedules

If compute constraints arise, consider these options:

**Peak hours only (8 runs/day):**
- 7am, 8am, 9am, 12pm, 4pm, 5pm, 6pm, 7pm
- Captures rush hours plus midday baseline
- Reduces costs by ~50% but loses midday granularity

**Every 2 hours (8 runs/day):**
- 5am, 7am, 9am, 11am, 1pm, 3pm, 5pm, 7pm
- Good for daily trends, insufficient for short-term delay analysis

Current hourly schedule is maintained because the cost difference is minimal ($4/year) and data density provides significantly more analytical value.

---

## Additional Resources

- **[Root README](../../README.md)** – Project overview and quickstart
- **[Pipeline Architecture](../ARCHITECTURE.md)** – How GTFS-RT fits into overall data flow
- **[dbt Models Documentation](../../dbt/models/README.md)** – How `stg_rt_events` transforms this data
- **[GitHub Workflows Documentation](../../.github/workflows/README.md)** – Technical workflow specifications
- **[QA Validation Guide](../QA_Validation_Guide.md)** – Coverage and freshness validation procedures
- **[Data Contracts](../contracts/CONTRACTS.md)** – Trip Updates and Vehicle Positions schemas

## External References

- [RTD GTFS-RT Developer Resources](https://www.rtd-denver.com/developer-resources/gtfs-realtime)
- [GTFS Realtime Reference](https://gtfs.org/realtime/)
- [Protocol Buffers Documentation](https://developers.google.com/protocol-buffers)
