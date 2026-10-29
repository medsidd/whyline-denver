# BigQuery naming and time conventions

## Layers and metadata

| Dataset | Contents |
|---|---|
| `raw_denver` | Nineteen registered `raw_*` source tables, normalized CSV loads, plus internal ingestion metadata |
| `stg_denver` | Silver `stg_*` models; obsolete `int_*` objects remain until an approved cleanup |
| `core_denver` | Gold-core dimensions, facts, and the stop-tract bridge |
| `mart_denver` | Nine `mart_*` analytic/reference tables plus export state where configured |

`src/whyline/load/registry.py` explicitly maps source globs, tables, ordered columns, partitioning, and clustering. The loader does not derive registrations from a table-name prefix or infer an arbitrary new CSV schema.

Each loaded raw record receives `_ingested_at` (UTC timestamp), `_source_path`, `_extract_date` (logical extract date), and `_hash_md5`. The ingestion log supports MD5-based skipping. `_extract_date` is lineage metadata, not proof every raw table partitions on that field.

## Physical partitioning

The registry partitions the realtime snapshot tables by `feed_ts_utc`, crashes by `event_ts_utc`, weather by `date`, and snapshot sources (static GTFS, ACS, sidewalks, tracts) by `_extract_date`. The four stream tables expire partitions after 90 days: trip-update changes and vehicle reports partition by `feed_ts_utc` (day), stop visits and trip status by `_ingested_at` (hour), so 15-minute reads prune to the newest loads. Inspect live table metadata after migrations rather than assuming it matches a former deployment.

`stg_rt_events` partitions by `event_date_mst`, `fct_stop_visit` and `fct_trip_status` by `service_date`; reliability/headway time-series tables use `service_date_mst`. Filter the physical partition field where possible. A filter on `_ingested_at` or a logical date can be semantically useful without pruning the source partition.

## Time semantics

UTC timestamp names such as `feed_ts_utc` and `event_ts_utc` preserve an absolute instant. Denver date/hour columns use `America/Denver`, including daylight saving time. The historical `_mst` suffix in column names means Denver local time, not fixed UTC−7.

GTFS times can exceed 24:00. `dbt/macros/` contains the conversion/calendar helpers; do not truncate late-night times modulo 24 without advancing the date. `fct_scheduled_stop_time` expands each service date from the GTFS snapshot current on that date and keeps past dates as published; nightly runs replace only today through +30 days.

`fct_stop_visit` and `fct_trip_status` take `service_date` from GTFS `start_date`, so a trip that runs past midnight belongs to the day it began; the reliability marts' `service_date_mst` is that service date. Their legacy partitions (before the stop-visit cutover) used the Denver date of the poll instead, which can differ for trips after midnight.

Loader Makefile date windows are UTC: before 06:00 UTC include yesterday, otherwise today. That cutoff is not 06:00 Mountain Time. GitHub cron expressions are UTC; user-facing operations reports specify their timezone explicitly.

See [pipeline](../technical/DATA_PIPELINE.md), [contracts](../contracts/CONTRACTS.md), and [models](../../dbt/models/README.md).
