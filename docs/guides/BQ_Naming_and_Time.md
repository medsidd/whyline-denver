# BigQuery Naming & Time Conventions

After a few early mistakes querying the wrong layer of data, I established strict naming conventions for this project. These rules apply across all BigQuery tables, dbt models, and Python ingestion scripts.

## Dataset & Table Naming

BigQuery has three datasets organized by the medallion architecture:

**`raw_denver`** — All tables prefixed with `raw_*`
- Examples: `raw_gtfs_routes`, `raw_gtfsrt_trip_updates`
- Contains unmodified CSV data loaded from GCS or local files
- No transformations, no cleanup

**`stg_denver`** — All tables prefixed with `stg_*`
- Examples: `stg_gtfs_routes`, `stg_rt_events`
- Deduplication, type casting, and basic cleanup
- Still close to source data

**`mart_denver`** — All tables prefixed with `mart_*`
- Examples: `mart_reliability_by_route_day`, `mart_weather_impacts`
- Denormalized, analysis-ready tables with joins and aggregations

The prefixes make it immediately obvious which layer you're working with. dbt can also select entire layers with `--select staging.*` which simplifies deployment.

**Important**: Don't create tables with custom prefixes like `tmp_*` or `test_*` in these datasets. The loader expects prefixes to match dataset names, and violating this will break freshness checks.

## Metadata Columns on Raw Tables

Every raw table receives four metadata columns automatically when you run `bq-load`:

| Column | Type | Purpose |
|--------|------|---------|
| `_ingested_at` | TIMESTAMP | When the loader wrote this row to BigQuery (UTC) |
| `_source_path` | STRING | GCS path or local file containing this data |
| `_extract_date` | DATE | Logical date extracted from the file path |
| `_hash_md5` | STRING | MD5 hash of the source file (prevents duplicate loads) |

The underscore prefix keeps these metadata columns grouped together in the BigQuery console, visually separated from actual data columns.

These columns have proven invaluable for debugging. When RTD published a malformed GTFS file in August, I traced it back to the exact ingestion run using `_source_path` in under a minute.

## Timezone Rules

Timezone handling follows a strict two-tier approach:

**Raw layer: UTC only**
- All timestamp columns end in `_utc`: `event_ts_utc`, `feed_ts_utc`, `arrival_ts_utc`
- Never convert timezones at the raw layer
- This prevents DST-related bugs like missing hours on time change days

**Staging layer: Add MST columns, preserve UTC**
- Create additional `_mst` columns for Denver local time
- Examples: `event_date_mst`, `event_hour_mst`
- Keep UTC originals for downstream models that need them

Example from `stg_rt_events`:
```sql
feed_ts_utc,                          -- Original UTC timestamp
DATE(feed_ts_utc, 'America/Denver') AS event_date_mst,
EXTRACT(HOUR FROM DATETIME(feed_ts_utc, 'America/Denver')) AS event_hour_mst
```

**Note**: Use `America/Denver` instead of `MST`. The former correctly handles daylight saving transitions, while `MST` is ambiguous and can cause off-by-one-hour errors during DST changes.

## Partitioning & Clustering

BigQuery charges per byte scanned, so partitioning and clustering significantly reduce costs.

**Partitioning** (for time-series tables):
- Partition by the primary timestamp: `DATE(event_ts_utc)` or `DATE(feed_ts_utc)`
- BigQuery physically separates data by day
- Queries with date filters only scan relevant partitions
- Applies to: `raw_gtfsrt_trip_updates`, `raw_gtfsrt_vehicle_positions`, `raw_weather_daily`, `raw_crashes`
- Skip for: Small dimension tables (<1GB)

**Clustering** (for frequently joined tables):
- Cluster by high-cardinality IDs: `route_id`, `trip_id`, `stop_id`
- BigQuery sorts data within each partition by these columns
- Dramatically speeds up filtered queries and joins

Example: `raw_gtfsrt_trip_updates` is partitioned by `DATE(feed_ts_utc)` and clustered by `trip_id`. A query for a specific trip on a specific day scans ~500KB instead of ~50MB.

**Rule of thumb**: Skip partitioning and clustering for tables under 1GB. The overhead isn't worth it for small tables.

## Why These Conventions Matter

Consistent conventions enable:

- **Parametric loading**: The `load/bq_load.py` script handles any new data source without code changes because it expects these four metadata columns
- **Simple staging models**: Most staging models are just `SELECT * FROM raw_* WHERE _rank = 1` with minimal transformations
- **Reliable freshness checks**: dbt freshness works because `_ingested_at` is always present
- **Fast debugging**: Any row can be traced back to its source file in seconds

---

## Additional Resources

- **[Root README](../../README.md)** – Project overview and quickstart
- **[Pipeline Architecture](../ARCHITECTURE.md)** – How data flows through these layers
- **[dbt Models Documentation](../../dbt/models/README.md)** – How staging models apply these conventions
- **[Data Contracts](../contracts/CONTRACTS.md)** – CSV schemas that define raw table structures
- **[GitHub Workflows Documentation](../../.github/workflows/README.md)** – Automation that enforces these conventions
