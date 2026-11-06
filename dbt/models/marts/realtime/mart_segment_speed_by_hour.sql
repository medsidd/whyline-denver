{{ config(
    materialized='table',
    cluster_by=['from_stop_id'],
    meta={"allow_in_app": true}
) }}

{#
Where buses and trains crawl: speed and running time between consecutive stops, by route,
direction, day type and hour of departure, over the last segment_window_days complete service
dates. lat and lon are the midpoint between the two stops, so the app maps segments as points.
Published after the stop-visit review.
#}
{% set window_days = var('segment_window_days', 28) %}

with grouped as (
    select
        from_stop_id,
        to_stop_id,
        route_id,
        direction_id,
        day_type,
        depart_hour_mst as hour_mst,
        count(*) as n_traversals,
        count(distinct service_date) as n_days,
        approx_quantiles(distance_m, 100)[offset(50)] as distance_m,
        approx_quantiles(speed_kmh, 100)[offset(50)] as p50_speed_kmh,
        approx_quantiles(speed_kmh, 100)[offset(10)] as p10_speed_kmh,
        approx_quantiles(travel_sec, 100)[offset(50)] as p50_travel_sec,
        approx_quantiles(travel_sec, 100)[offset(90)] as p90_travel_sec,
        approx_quantiles(scheduled_travel_sec, 100)[offset(50)] as scheduled_travel_sec
    from {{ ref('fct_segment_traversal') }}
    where service_date between date_sub(current_date('America/Denver'), interval {{ window_days }} day)
        and date_sub(current_date('America/Denver'), interval 1 day)
    group by 1, 2, 3, 4, 5, 6
)

select
    g.from_stop_id,
    a.stop_name as from_stop_name,
    g.to_stop_id,
    b.stop_name as to_stop_name,
    (a.lat + b.lat) / 2 as lat,
    (a.lon + b.lon) / 2 as lon,
    g.route_id,
    g.direction_id,
    g.day_type,
    g.hour_mst,
    g.n_traversals,
    g.n_days,
    g.distance_m,
    g.p50_speed_kmh,
    g.p10_speed_kmh,
    g.p50_travel_sec,
    g.p90_travel_sec,
    g.scheduled_travel_sec,
    -- NULL where the schedule gives both stops the same minute.
    safe_divide(g.p50_travel_sec, nullif(g.scheduled_travel_sec, 0)) as delay_ratio,
    current_timestamp() as build_run_at
from grouped as g
left join {{ ref('dim_stop') }} as a
    on a.stop_id = g.from_stop_id
    and a.is_current
left join {{ ref('dim_stop') }} as b
    on b.stop_id = g.to_stop_id
    and b.is_current
