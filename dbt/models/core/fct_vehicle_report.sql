{{ config(materialized='view') }}

{#
Every distinct vehicle report from the continuous stream, for the live marts (marts read only
gold core). A view over stg_rt_vehicle_positions: a filter on feed_ts_utc prunes the raw
partitions (90-day expiry), so readers must filter it. Reports arrive in 15-minute batches,
so the newest is 15–30 minutes old.
#}
select
    feed_ts_utc,
    report_ts_utc,
    vehicle_id,
    vehicle_label,
    trip_id,
    service_date,
    route_id,
    direction_id,
    stop_id,
    current_status,
    lat,
    lon,
    bearing,
    speed_mps,
    occupancy_status,
    report_age_sec
from {{ ref('stg_rt_vehicle_positions') }}
