{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": false}
) }}

{#
Ghost buses: what happened to every scheduled trip, per route, direction, service date and the
period it was scheduled to start in. A trip is delivered when a vehicle reported on it and it
reached at least one stop. Trips are observable when every 15-minute window from 10 minutes
before their scheduled start to their scheduled end had a healthy feed (fct_stream_health);
shares count observable trips only. Shares are withheld for routes whose vehicles rarely report
at all (pct_tracked_with_vehicle under 0.8 over 28 days): on 2026-10-30 only 3 N Line trains
reported, so most N Line trips looked missed. Published after the stop-visit review.
#}
{% set days = var('service_delivered_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('service_delivered_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with scheduled as (
    select
        service_date_mst as service_date,
        trip_id,
        any_value(route_id) as route_id,
        any_value(direction_id) as direction_id,
        min(sched_departure_ts_mst) as start_ts,
        max(sched_arrival_ts_mst) as end_ts
    from {{ ref('fct_scheduled_stop_time') }}
    where service_date_mst between {{ first }} and {{ last }}
    group by 1, 2
),
trips as (
    select
        s.*,
        case
            when t.outcome is null then 'not_tracked'
            when t.outcome = 'canceled' then 'canceled'
            -- Visits inferred from predictions alone don't show a vehicle ran.
            when not t.had_vehicle then 'no_vehicle'
            when t.outcome in ('completed', 'partial') then 'delivered'
            else 'vehicle_no_visits'
        end as delivery,
        case
            when {{ hour_mst('s.start_ts') }} between 4 and 6 then 'early'
            when {{ hour_mst('s.start_ts') }} between 7 and 8 then 'am_peak'
            when {{ hour_mst('s.start_ts') }} between 9 and 14 then 'midday'
            when {{ hour_mst('s.start_ts') }} between 15 and 17 then 'pm_peak'
            when {{ hour_mst('s.start_ts') }} between 18 and 20 then 'evening'
            else 'night'
        end as period
    from scheduled as s
    left join {{ ref('fct_trip_status') }} as t
        on t.service_date = s.service_date
        and t.trip_id = s.trip_id
        and t.service_date between {{ first }} and {{ last }}
),
vehicle_reporting as (
    select
        route_id,
        avg(if(had_vehicle, 1, 0)) as pct_tracked_with_vehicle
    from {{ ref('fct_trip_status') }}
    where
        service_date between date_sub({{ last }}, interval 27 day) and {{ last }}
        and outcome not in ('canceled', 'no_static')
    group by 1
),
observable as (
    select
        t.service_date,
        t.trip_id,
        logical_and(coalesce(h.is_healthy, false)) as is_observable
    from trips as t
    left join {{ ref('fct_stream_health') }} as h
        on h.window_start_utc > timestamp_sub(t.start_ts, interval 25 minute)
        and h.window_start_utc <= t.end_ts
        and h.window_date_utc between date_sub({{ first }}, interval 1 day)
        and date_add({{ last }}, interval 2 day)
    group by 1, 2
)

select
    t.route_id,
    t.direction_id,
    t.service_date as service_date_mst,
    t.period,
    count(*) as n_scheduled,
    countif(t.delivery = 'delivered') as n_delivered,
    countif(t.delivery = 'canceled') as n_canceled,
    countif(t.delivery = 'no_vehicle') as n_no_vehicle,
    countif(t.delivery = 'vehicle_no_visits') as n_vehicle_no_visits,
    countif(t.delivery = 'not_tracked') as n_not_tracked,
    countif(o.is_observable) as n_observable,
    countif(o.is_observable) = count(*) as stream_healthy,
    any_value(v.pct_tracked_with_vehicle) as pct_tracked_with_vehicle,
    if(
        any_value(v.pct_tracked_with_vehicle) >= 0.8,
        safe_divide(countif(o.is_observable and t.delivery = 'delivered'), countif(o.is_observable)),
        null
    ) as pct_delivered,
    if(
        any_value(v.pct_tracked_with_vehicle) >= 0.8,
        safe_divide(
            countif(o.is_observable and t.delivery in ('canceled', 'no_vehicle', 'not_tracked')),
            countif(o.is_observable)
        ),
        null
    ) as pct_missed_likely,
    current_timestamp() as build_run_at
from trips as t
join observable as o
    on o.service_date = t.service_date
    and o.trip_id = t.trip_id
left join vehicle_reporting as v
    on v.route_id = t.route_id
where t.route_id is not null
group by 1, 2, 3, 4
