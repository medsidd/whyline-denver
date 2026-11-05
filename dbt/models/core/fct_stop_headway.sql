{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date', 'data_type': 'date'},
    cluster_by=['route_id', 'stop_id'],
    on_schema_change='append_new_columns'
) }}

{#
Observed headways: for each stop visit a vehicle made, the time since the previous vehicle of
the same route and direction reached the stop that service day, next to the scheduled headway
of the arriving trip. Visits timed from the last prediction count only when the trip had a
vehicle, so a ghost trip leaves the gap riders saw; skipped stops have no arrival. Rebuildable
from fct_stop_visit; nightly runs replace the last wait_days service dates.
#}
{% set days = var('wait_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('wait_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with visits as (
    select
        v.service_date,
        v.stop_id,
        v.route_id,
        v.direction_id,
        v.trip_id,
        v.stop_sequence,
        v.arrival_method,
        v.arrival_ts_utc,
        v.scheduled_headway_sec,
        v.delay_sec,
        lag(v.arrival_ts_utc) over (
            partition by v.service_date, v.route_id, v.direction_id, v.stop_id
            order by v.arrival_ts_utc, v.trip_id
        ) as previous_arrival_ts
    from {{ ref('fct_stop_visit') }} as v
    left join {{ ref('fct_trip_status') }} as t
        on t.service_date = v.service_date
        and t.trip_id = v.trip_id
        and t.service_date between {{ first }} and {{ last }}
    where
        v.service_date between {{ first }} and {{ last }}
        and v.arrival_ts_utc is not null
        and (
            v.arrival_method in ('shape_crossing', 'shape_crossing_gap', 'origin_departure')
            or (v.arrival_method = 'last_prediction' and coalesce(t.had_vehicle, false))
        )
)

select
    service_date,
    stop_id,
    route_id,
    direction_id,
    trip_id,
    stop_sequence,
    arrival_method,
    arrival_ts_utc,
    case format_date('%u', service_date)
        when '6' then 'saturday'
        when '7' then 'sunday'
        else 'weekday'
    end as day_type,
    case
        when {{ hour_mst('arrival_ts_utc') }} between 4 and 6 then 'early'
        when {{ hour_mst('arrival_ts_utc') }} between 7 and 8 then 'am_peak'
        when {{ hour_mst('arrival_ts_utc') }} between 9 and 14 then 'midday'
        when {{ hour_mst('arrival_ts_utc') }} between 15 and 17 then 'pm_peak'
        when {{ hour_mst('arrival_ts_utc') }} between 18 and 20 then 'evening'
        else 'night'
    end as period,
    timestamp_diff(arrival_ts_utc, previous_arrival_ts, second) as observed_headway_sec,
    scheduled_headway_sec,
    delay_sec
from visits
where route_id is not null
