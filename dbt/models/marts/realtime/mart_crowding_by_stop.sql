{{ config(
    materialized='table',
    cluster_by=['stop_id'],
    meta={"allow_in_app": false}
) }}

{#
Load points: how often vehicles arrived at each stop with few seats or standing room only, by
route, direction, weekday or weekend and hour, over the last crowding_window_days complete
service dates. Levels are the highest reported on the way to or at the stop. Shares count only
visits with occupancy data. Published after the coverage check; until then allow_in_app is false.
#}
{% set window_days = var('crowding_window_days', 28) %}

with visits as (
    select
        stop_id,
        route_id,
        direction_id,
        if(format_date('%u', service_date) in ('6', '7'), 'weekend', 'weekday') as day_type,
        {{ hour_mst('event_ts_utc') }} as hour_mst,
        service_date,
        max_level
    from {{ ref('fct_trip_occupancy') }}
    where
        service_date between date_sub(current_date('America/Denver'), interval {{ window_days }} day)
        and date_sub(current_date('America/Denver'), interval 1 day)
        and route_id is not null
        and event_ts_utc is not null
)

select
    v.stop_id,
    st.stop_name,
    st.lat,
    st.lon,
    v.route_id,
    v.direction_id,
    v.day_type,
    v.hour_mst,
    count(*) as n_visits,
    countif(v.max_level is not null) as n_visits_with_data,
    countif(v.max_level is not null) / count(*) as pct_visits_with_data,
    avg(if(v.max_level is null, null, if(v.max_level >= 2, 1, 0))) as pct_few_seats_or_worse,
    avg(if(v.max_level is null, null, if(v.max_level >= 3, 1, 0))) as pct_standing_or_worse,
    min(v.service_date) as first_service_date,
    max(v.service_date) as last_service_date,
    current_timestamp() as build_run_at
from visits as v
left join {{ ref('dim_stop') }} as st
    on st.stop_id = v.stop_id
    and st.is_current
group by 1, 2, 3, 4, 5, 6, 7, 8
