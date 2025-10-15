{{ config(materialized='view') }}

with base as (
    select
        trip_id,
        stop_id,
        stop_sequence,
        arrival_time,
        departure_time
    from {{ source('raw','raw_gtfs_stop_times') }}
),
norm as (
    select
        *,
        split(arrival_time, ':')[offset(0)] as a_h,
        split(arrival_time, ':')[offset(1)] as a_m,
        split(arrival_time, ':')[offset(2)] as a_s,
        split(departure_time, ':')[offset(0)] as d_h,
        split(departure_time, ':')[offset(1)] as d_m,
        split(departure_time, ':')[offset(2)] as d_s
    from base
)
select
    trip_id,
    stop_id,
    stop_sequence,
    cast(a_h as int64) as arr_hour_gtfs,
    cast(d_h as int64) as dep_hour_gtfs,
    case
        when cast(a_h as int64) is null then null
        else cast(a_h as int64)
    end as arr_hour_bucket
from norm
