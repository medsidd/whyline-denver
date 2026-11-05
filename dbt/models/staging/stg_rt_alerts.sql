{{ config(materialized='view') }}

{#
Silver: RTD service alerts as snapshotted every 15 minutes, one row per alert and informed
entity per snapshot. Filter feed_ts_utc with a constant so BigQuery prunes the raw partitions
(90-day expiry).
#}
select
    feed_ts_utc,
    alert_id,
    cause,
    effect,
    header_text,
    description_text,
    url,
    agency_id,
    route_id,
    route_type,
    direction_id,
    stop_id,
    trip_id
from {{ source('raw', 'raw_gtfsrt_alerts') }}
where alert_id is not null
