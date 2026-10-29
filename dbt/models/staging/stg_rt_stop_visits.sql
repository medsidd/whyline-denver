{{ config(materialized='view') }}

{#
Silver: stop visits derived by the poller (stream_v1) or the backfill (backfill_v1), typed.
The poller emits only final visits; core.fct_stop_visit conforms them. Filter _ingested_at
with a constant: the raw table is partitioned by load hour and expires after 90 days.
#}
select
    service_date,
    trip_id,
    start_date,
    stop_sequence,
    stop_id,
    stop_role,
    route_id,
    direction_id,
    trip_headsign,
    vehicle_id,
    arrival_method,
    arrival_ts_utc,
    arrival_earliest_ts,
    arrival_latest_ts,
    departure_earliest_ts,
    departure_latest_ts,
    dwell_min_sec,
    dwell_max_sec,
    skipped,
    stopped_observed,
    before_report_ts,
    before_dist_along_m,
    after_report_ts,
    after_dist_along_m,
    stop_dist_m,
    nearest_offset_m,
    last_predicted_arrival_ts,
    last_prediction_published_ts,
    trip_switch_at_terminal,
    low_confidence,
    is_final,
    data_version,
    static_md5,
    emitted_at,
    _ingested_at
from {{ source('raw', 'raw_gtfsrt_stop_visits') }}
where trip_id is not null
  and service_date is not null
  and stop_sequence is not null
