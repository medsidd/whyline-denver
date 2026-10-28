# BigQuery naming and time conventions

## Layers and metadata

| Dataset | Contents |
|---|---|
| `raw_denver` | Fourteen registered `raw_*` source tables, normalized CSV loads, plus internal ingestion metadata |
| `stg_denver` | Both `stg_*` and `int_*` models |
| `mart_denver` | Nine `mart_*` analytic/reference tables plus export state where configured |

`src/whyline/load/registry.py` explicitly maps source globs, tables, ordered columns, partitioning, and clustering. The loader does not derive registrations from a table-name prefix or infer an arbitrary new CSV schema.

Each loaded raw record receives `_ingested_at` (UTC timestamp), `_source_path`, `_extract_date` (logical extract date), and `_hash_md5`. The ingestion log supports MD5-based skipping. `_extract_date` is lineage metadata, not proof every raw table partitions on that field.

## Physical partitioning

The current registry partitions realtime trip/vehicle tables by `feed_ts_utc`, crashes by `event_ts_utc`, and weather by `date`. Static GTFS, ACS, sidewalks, and tracts have no partition configured in the registry. Inspect live table metadata after migrations rather than assuming it matches a former deployment.

`stg_rt_events` partitions by `event_date_mst`; reliability/headway time-series tables use `service_date_mst`. Filter the physical partition field where possible. A filter on `_ingested_at` or a logical date can be semantically useful without pruning the source partition.

## Time semantics

UTC timestamp names such as `feed_ts_utc` and `event_ts_utc` preserve an absolute instant. Denver date/hour columns use `America/Denver`, including daylight saving time. The historical `_mst` suffix in column names means Denver local time, not fixed UTC−7.

GTFS times can exceed 24:00. `dbt/macros/` contains the conversion/calendar helpers; do not truncate late-night times modulo 24 without advancing the date. `fct_scheduled_stop_time` expands each service date from the GTFS snapshot current on that date and keeps past dates as published; nightly runs replace only today through +30 days.

Realtime service dates in the current model are derived from the event timestamp in Denver time. This can differ from an agency's operational service-day assignment for trips after midnight. Review SQL before treating a service-date label as an exact GTFS `start_date` match.

Loader Makefile date windows are UTC: before 06:00 UTC include yesterday, otherwise today. That cutoff is not 06:00 Mountain Time. GitHub cron expressions are UTC; user-facing operations reports specify their timezone explicitly.

See [pipeline](../technical/DATA_PIPELINE.md), [contracts](../contracts/CONTRACTS.md), and [models](../../dbt/models/README.md).
