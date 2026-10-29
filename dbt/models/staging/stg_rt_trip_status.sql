{{ config(materialized='view') }}

{#
Silver: one row per trip instance the poller closed (absent from both feeds for 10 minutes),
typed. Filter _ingested_at with a constant: partitioned by load hour, 90-day expiry.
#}
select
    service_date,
    trip_id,
    start_date,
    route_id,
    direction_id,
    final_schedule_relationship,
    outcome,
    first_seen_ts,
    last_seen_ts,
    first_vp_ts,
    last_vp_ts,
    had_vehicle,
    n_stops_static,
    n_visits,
    n_shape_crossing,
    n_last_prediction,
    n_skipped,
    data_version,
    static_md5,
    closed_at,
    _ingested_at
from {{ source('raw', 'raw_gtfsrt_trip_status') }}
where trip_id is not null
  and service_date is not null
