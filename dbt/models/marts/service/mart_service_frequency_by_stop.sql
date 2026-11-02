{{ config(
    materialized='table',
    cluster_by=['stop_id'],
    meta={"allow_in_app": true}
) }}

{#
Scheduled departures by stop, route, direction and hour of day, for the next Wednesday, Saturday
and Sunday in the published schedule. Trips after midnight count in hours 0-3 of their service day.
#}
with sample_dates as (
    {{ schedule_sample_dates() }}
),
departures as (
    select
        d.day_type,
        d.sample_date,
        s.stop_id,
        s.route_id,
        s.direction_id,
        {{ hour_mst('s.sched_departure_ts_mst') }} as hour_mst,
        count(*) as n_departures
    from {{ ref('fct_scheduled_stop_time') }} as s
    join sample_dates as d
        on s.service_date_mst = d.sample_date
    where
        -- Repeats the sample window so BigQuery prunes the schedule partitions.
        s.service_date_mst between current_date('America/Denver')
        and date_add(current_date('America/Denver'), interval 13 day)
    group by 1, 2, 3, 4, 5, 6
)

select
    d.day_type,
    d.sample_date,
    d.stop_id,
    st.stop_name,
    st.lat,
    st.lon,
    d.route_id,
    r.route_name,
    d.direction_id,
    d.hour_mst,
    d.n_departures,
    round(60 / d.n_departures, 1) as avg_headway_min,
    current_timestamp() as build_run_at
from departures as d
left join {{ ref('dim_stop') }} as st
    on st.stop_id = d.stop_id
    and st.is_current
left join {{ ref('dim_route') }} as r
    on r.route_id = d.route_id
    and r.is_latest_version
