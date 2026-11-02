{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
"Report card for route 15": one row per route, both directions together, over the last
scorecard_window_days service dates: scheduled frequency and span, on-time share and excess wait,
delivered and likely-missed trips, prediction accuracy, crowding, run-time reliability and alert
hours. Each measured component comes with its count; a missing component stays NULL, never 0.
Published with release R4.
#}
{% set window_days = var('scorecard_window_days', 28) %}
{% set since = "date_sub(current_date('America/Denver'), interval " ~ window_days ~ " day)" %}
{% set until = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with routes as (
    select route_id, route_name, route_long_name
    from {{ ref('dim_route') }}
    where is_latest_version and route_id is not null
),
schedule as (
    select
        route_id,
        logical_and(is_frequent_route) as is_frequent_route,
        min(if(day_type = 'weekday', first_departure, null)) as weekday_first_departure,
        max(if(day_type = 'weekday', last_departure, null)) as weekday_last_departure,
        avg(if(day_type = 'weekday', headway_midday_min, null)) as weekday_midday_headway_min
    from {{ ref('mart_frequent_network_by_route') }}
    group by 1
),
reliability as (
    select
        route_id,
        count(*) as n_visits_measured,
        avg(if(delay_sec is null, null,
            if(delay_sec between -{{ var('on_time_early_sec', 60) }} and {{ var('on_time_late_sec', 300) }}, 1, 0))) as pct_on_time,
        safe_divide(
            sum(if(scheduled_headway_sec between 1 and 900, pow(observed_headway_sec, 2), null)),
            2 * sum(if(scheduled_headway_sec between 1 and 900, observed_headway_sec, null))
        ) - safe_divide(
            sum(if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, pow(scheduled_headway_sec, 2), null)),
            2 * sum(if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, scheduled_headway_sec, null))
        ) as excess_wait_sec
    from {{ ref('fct_stop_headway') }}
    where service_date between {{ since }} and {{ until }}
    group by 1
),
delivery as (
    select
        route_id,
        sum(n_scheduled) as n_trips_scheduled,
        sum(n_observable) as n_trips_observable,
        safe_divide(sum(pct_delivered * n_observable), sum(if(pct_delivered is null, 0, n_observable))) as pct_delivered,
        safe_divide(sum(pct_missed_likely * n_observable), sum(if(pct_missed_likely is null, 0, n_observable)))
            as pct_missed_likely
    from {{ ref('mart_service_delivered_by_route_day') }}
    where service_date_mst between {{ since }} and {{ until }}
    group by 1
),
predictions as (
    select
        route_id,
        avg(if(has_prediction and horizon_bucket = '0-3', if(within_band, 1, 0), null)) as pct_predictions_accurate_0_3
    from {{ ref('fct_prediction_accuracy') }}
    where service_date between {{ since }} and {{ until }}
    group by 1
),
crowding as (
    select
        route_id,
        count(*) as n_trips_with_occupancy,
        avg(if(trip_level >= 3, 1, 0)) as pct_trips_standing_or_worse
    from (
        select service_date, trip_id, any_value(route_id) as route_id, max(max_level) as trip_level
        from {{ ref('fct_trip_occupancy') }}
        where service_date between {{ since }} and {{ until }}
        group by 1, 2
    )
    where trip_level is not null
    group by 1
),
runtime as (
    select
        route_id,
        sum(n_trips) as n_trips_timed,
        round(safe_divide(sum(buffer_time_index * n_trips), sum(n_trips)), 3) as buffer_time_index
    from {{ ref('mart_trip_runtime_by_route_day') }}
    where service_date_mst between {{ since }} and {{ until }}
    group by 1
),
alerts as (
    select route_id, round(sum(alert_hours), 1) as alert_hours
    from {{ ref('mart_alerts_by_route_day') }}
    where service_date_mst between {{ since }} and {{ until }}
    group by 1
)

select
    r.route_id,
    r.route_name,
    r.route_long_name,
    s.is_frequent_route,
    s.weekday_first_departure,
    s.weekday_last_departure,
    round(s.weekday_midday_headway_min, 1) as weekday_midday_headway_min,
    rl.n_visits_measured,
    rl.pct_on_time,
    rl.excess_wait_sec,
    d.n_trips_scheduled,
    d.n_trips_observable,
    d.pct_delivered,
    d.pct_missed_likely,
    p.pct_predictions_accurate_0_3,
    c.n_trips_with_occupancy,
    c.pct_trips_standing_or_worse,
    rt.n_trips_timed,
    rt.buffer_time_index,
    a.alert_hours,
    current_timestamp() as build_run_at
from routes as r
left join schedule as s using (route_id)
left join reliability as rl using (route_id)
left join delivery as d using (route_id)
left join predictions as p using (route_id)
left join crowding as c using (route_id)
left join runtime as rt using (route_id)
left join alerts as a using (route_id)
