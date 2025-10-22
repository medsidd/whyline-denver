{{ config(materialized='view') }}

with base as (
    select
        route_id,
        trip_id,
        stop_id,
        direction_id,
        event_date_mst as service_date_mst,
        event_hour_mst,
        event_ts_utc,
        arrival_delay_sec,
        departure_delay_sec,
        coalesce(arrival_delay_sec, departure_delay_sec) as delay_sec_raw,
        coalesce(arrival_delay_sec, departure_delay_sec, 0) as delay_sec
    from {{ ref('stg_rt_events') }}
)

select
    route_id,
    trip_id,
    stop_id,
    direction_id,
    service_date_mst,
    event_hour_mst,
    event_ts_utc,
    delay_sec,
    delay_sec_raw,
    case
        when abs(delay_sec) <= {{ var('on_time_sec', 300) }} then 1
        else 0
    end as is_on_time
from base
