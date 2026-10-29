{{ config(materialized='view') }}

{#
Silver evidence: every distinct vehicle report from the continuous stream, without repeats,
reports more than 120 s older than their feed header, or positions outside the Denver box.
No 15-minute model reads this view; validation queries filter feed_ts_utc with a constant,
and with no window functions here the filter prunes the raw partitions (90-day expiry).
dist_along_m / lateral_offset_m are the poller's projection onto the trip shape.
#}
select
    feed_ts_utc,
    report_ts_utc,
    vehicle_id,
    vehicle_label,
    trip_id,
    start_date,
    safe.parse_date('%Y%m%d', start_date) as service_date,
    route_id,
    direction_id,
    stop_id,
    current_status,
    lat,
    lon,
    {{ make_point('lon', 'lat') }} as geom,
    bearing,
    speed_mps,
    occupancy_status,
    report_age_sec,
    dist_along_m,
    lateral_offset_m,
    valid_for_timing,
    _ingested_at
from {{ source('raw', 'raw_gtfsrt_vp_stream') }}
where not is_repeat
  and in_bbox
  and report_age_sec <= 120
