{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date', 'data_type': 'date'},
    cluster_by=['route_id', 'from_stop_id'],
    on_schema_change='append_new_columns'
) }}

{#
Running time between consecutive stops of a trip: from leaving stop n (the middle of its
departure window, or its arrival when the vehicle didn't stop) to reaching stop n+1. Both ends
must be timed to within 30 s, and speeds over 130 km/h (faster than any RTD vehicle) are timing
error and dropped. Distance is along the trip's shape, so speed is the vehicle's average between
the stops, dwell excluded. Rebuildable from fct_stop_visit; nightly runs
replace the last segment_days service dates.
#}
{% set days = var('segment_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('segment_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with visits as (
    select
        service_date,
        trip_id,
        route_id,
        direction_id,
        stop_sequence,
        stop_id,
        within_30s,
        stop_dist_m,
        arrival_ts_utc,
        if(
            stop_role != 'first' and departure_earliest_ts is not null,
            timestamp_add(
                departure_earliest_ts,
                interval (div(timestamp_diff(departure_latest_ts, departure_earliest_ts, second), 2)) second
            ),
            arrival_ts_utc
        ) as depart_ts_utc,
        coalesce(scheduled_departure_ts, scheduled_arrival_ts) as scheduled_depart_ts,
        coalesce(scheduled_arrival_ts, scheduled_departure_ts) as scheduled_arrive_ts
    from {{ ref('fct_stop_visit') }}
    where service_date between {{ first }} and {{ last }}
),
pairs as (
    select
        *,
        lead(stop_sequence) over trip_order as to_stop_sequence,
        lead(stop_id) over trip_order as to_stop_id,
        lead(within_30s) over trip_order as to_within_30s,
        lead(stop_dist_m) over trip_order as to_stop_dist_m,
        lead(arrival_ts_utc) over trip_order as arrive_ts_utc,
        lead(scheduled_arrive_ts) over trip_order as to_scheduled_arrive_ts
    from visits
    window trip_order as (partition by service_date, trip_id order by stop_sequence)
)

select
    service_date,
    trip_id,
    route_id,
    direction_id,
    stop_sequence as from_stop_sequence,
    stop_id as from_stop_id,
    to_stop_sequence,
    to_stop_id,
    case format_date('%u', service_date)
        when '6' then 'saturday'
        when '7' then 'sunday'
        else 'weekday'
    end as day_type,
    {{ hour_mst('depart_ts_utc') }} as depart_hour_mst,
    depart_ts_utc,
    arrive_ts_utc,
    timestamp_diff(arrive_ts_utc, depart_ts_utc, second) as travel_sec,
    timestamp_diff(to_scheduled_arrive_ts, scheduled_depart_ts, second) as scheduled_travel_sec,
    to_stop_dist_m - stop_dist_m as distance_m,
    round(3.6 * (to_stop_dist_m - stop_dist_m) / timestamp_diff(arrive_ts_utc, depart_ts_utc, second), 1)
        as speed_kmh
from pairs
where
    within_30s
    and to_within_30s
    and route_id is not null
    and to_stop_dist_m > stop_dist_m
    and arrive_ts_utc > depart_ts_utc
    -- Timing error on stops a few seconds apart yields impossible speeds (0.7% over 120 km/h).
    and 3.6 * (to_stop_dist_m - stop_dist_m) / timestamp_diff(arrive_ts_utc, depart_ts_utc, second) <= 130
