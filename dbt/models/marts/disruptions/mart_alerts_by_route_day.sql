{{ config(materialized='table', cluster_by=['route_id'], meta={"allow_in_app": false}) }}

{#
How much of each day each route was under a service alert, by effect: alerts in effect, alert
hours (each alert's overlap with the local day, so two alerts at once count twice), and stops
named. Days run from alerts_start (when snapshots began) to today. Published with release R2.
#}
with intervals as (
    select distinct
        alert_id,
        route_id,
        coalesce(effect, 'UNKNOWN_EFFECT') as effect,
        stop_id,
        start_ts,
        coalesce(end_ts, current_timestamp()) as end_ts
    from ({{ alert_intervals() }})
    where route_id is not null
),
days as (
    select
        d as service_date_mst,
        timestamp(d, 'America/Denver') as day_start,
        timestamp(date_add(d, interval 1 day), 'America/Denver') as day_end
    from unnest(generate_date_array(date '{{ var("alerts_start", "2026-11-02") }}', current_date('America/Denver'))) as d
),
by_day as (
    select i.*, d.service_date_mst, d.day_start, d.day_end
    from intervals as i
    join days as d
        on i.start_ts < d.day_end
        and i.end_ts > d.day_start
),
alert_hours as (
    -- Each period once per alert and route, whatever the number of stops it names.
    select
        route_id,
        service_date_mst,
        effect,
        alert_id,
        sum(timestamp_diff(least(end_ts, day_end), greatest(start_ts, day_start), second)) / 3600 as hours
    from (select distinct route_id, service_date_mst, effect, alert_id, start_ts, end_ts, day_start, day_end from by_day)
    group by 1, 2, 3, 4
),
stops as (
    select route_id, service_date_mst, effect, count(distinct stop_id) as n_stops_named
    from by_day
    group by 1, 2, 3
)

select
    h.route_id,
    h.service_date_mst,
    h.effect,
    count(*) as n_alerts,
    round(sum(h.hours), 2) as alert_hours,
    any_value(s.n_stops_named) as n_stops_named,
    current_timestamp() as build_run_at
from alert_hours as h
left join stops as s
    on s.route_id = h.route_id
    and s.service_date_mst = h.service_date_mst
    and s.effect = h.effect
group by 1, 2, 3
