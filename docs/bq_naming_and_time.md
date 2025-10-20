# BigQuery Naming & Time Conventions

These conventions keep loaders simple, dbt models predictable, and downstream tests reliable. They apply to all BigQuery assets managed by WhyLine Denver.

## Datasets & Table Names
- Raw tables live in the `raw_denver` dataset and are prefixed `raw_*`.
- Staging models materialize in the `stg_denver` dataset and are prefixed `stg_*`.
- Downstream marts may add other prefixes, but must never reuse `raw_` or `stg_`.

## Required Raw Meta Columns
Every raw table includes a consistent ingestion footprint with the following columns and types:

| Column | Type | Description |
| --- | --- | --- |
| `_ingested_at` | `TIMESTAMP` | UTC timestamp when the loader wrote this record. |
| `_source_path` | `STRING` | Original file path or GCS URI for traceability. |
| `_extract_date` | `DATE` | Logical extract date derived from file metadata or directory names. |
| `_hash_md5` | `STRING` | MD5 hash of raw file contents used for idempotency checks. |

## Timezone Rules
- All raw-layer timestamps are stored in UTC and carry a `_utc` suffix (for example, `event_ts_utc`, `feed_ts_utc`).
- Staging models handle any conversions to `America/Denver`, creating additional columns as needed without dropping the UTC originals.

## Partitioning & Clustering
- Large fact tables (GTFS-RT events, crashes, other time-series facts) are partitioned by the relevant UTC date column (`DATE(event_ts_utc)` or `DATE(feed_ts_utc)`).
- Clustering keys should prioritize high-cardinality join identifiers such as `route_id`, `trip_id`, or `stop_id`.
- For smaller dimension tables, skip partitioning unless repeated scans prove it helpful; clustering is optional but should follow the same key guidance.

Adhering to this schema keeps the loaders parametric, staging models thin, and freshness tests trustworthy.
