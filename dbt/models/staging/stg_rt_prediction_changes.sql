{{ config(materialized='view') }}

{#
Silver evidence: the stream's trip-update history as changes only. A stop row appears when it
is first listed (new), when its predicted times or relationship change (changed), and when it
leaves a trip that is still listed (dropped, carrying the last emitted values); trip-level rows
have no stop_sequence. A poller restart re-emits identical rows as new, which is harmless.
Filter feed_ts_utc with a constant so BigQuery prunes the raw partitions (90-day expiry).
#}
select
    feed_ts_utc,
    change_type,
    trip_id,
    start_date,
    safe.parse_date('%Y%m%d', start_date) as service_date,
    route_id,
    direction_id,
    trip_schedule_relationship,
    tu_timestamp_utc,
    tu_vehicle_id,
    stop_sequence,
    stop_id,
    arrival_ts_utc,
    departure_ts_utc,
    coalesce(arrival_ts_utc, departure_ts_utc) as predicted_ts_utc,
    arrival_delay_sec,
    departure_delay_sec,
    stop_schedule_relationship,
    stop_sequence is null as is_trip_level,
    _ingested_at
from {{ source('raw', 'raw_gtfsrt_tu_changes') }}
