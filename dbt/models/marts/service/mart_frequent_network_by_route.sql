{{ config(materialized='table', meta={"allow_in_app": true}) }}

{#
Span and frequency per route, direction and day type, measured at each direction's busiest stop
(the most scheduled departures that day), so short turns count. "Frequent" follows TransitCenter:
every 15 minutes or better from 6:00 to 21:00 on all three day types, tested as at least 12
departures in each three-hour block, so a departure slipping past a clock hour doesn't count against it.
#}
with sample_dates as (
    {{ schedule_sample_dates() }}
),
stop_hours as (
    select
        d.day_type,
        d.sample_date,
        s.route_id,
        s.direction_id,
        s.stop_id,
        {{ hour_mst('s.sched_departure_ts_mst') }} as hour_mst,
        count(*) as n_departures,
        min(s.sched_departure_ts_mst) as first_departure_ts,
        max(s.sched_departure_ts_mst) as last_departure_ts
    from {{ ref('fct_scheduled_stop_time') }} as s
    join sample_dates as d
        on s.service_date_mst = d.sample_date
    where
        s.service_date_mst between current_date('America/Denver')
        and date_add(current_date('America/Denver'), interval 13 day)
    group by 1, 2, 3, 4, 5, 6
),
trunk_stop as (
    select
        day_type,
        route_id,
        direction_id,
        stop_id
    from stop_hours
    group by 1, 2, 3, 4
    qualify row_number() over (
        partition by day_type, route_id, direction_id
        order by sum(n_departures) desc, stop_id
    ) = 1
),
trunk_hours as (
    select h.*
    from stop_hours as h
    join trunk_stop as t
        using (day_type, route_id, direction_id, stop_id)
),
-- Blocks with no departure at all count as zero for the frequency test.
blocks as (
    select block from unnest(generate_array(0, 4)) as block
),
block_counts as (
    select
        day_type,
        route_id,
        direction_id,
        div(hour_mst - 6, 3) as block,
        sum(n_departures) as n_departures
    from trunk_hours
    where hour_mst between 6 and 20
    group by 1, 2, 3, 4
),
frequency as (
    select
        t.day_type,
        t.route_id,
        t.direction_id,
        min(coalesce(c.n_departures, 0)) as min_departures_per_3h
    from (select distinct day_type, route_id, direction_id from trunk_hours) as t
    cross join blocks as b
    left join block_counts as c
        on c.day_type = t.day_type
        and c.route_id = t.route_id
        and c.direction_id = t.direction_id
        and c.block = b.block
    group by 1, 2, 3
),
-- Frequent only when every direction is frequent on all three day types.
route_flags as (
    select
        route_id,
        logical_and(min_departures_per_3h >= 12) and count(distinct day_type) = 3 as is_frequent_route
    from frequency
    group by 1
),
per_direction as (
    select
        h.day_type,
        h.sample_date,
        h.route_id,
        h.direction_id,
        h.stop_id as busiest_stop_id,
        sum(h.n_departures) as n_departures_busiest_stop,
        format_datetime('%H:%M', {{ as_mst('min(h.first_departure_ts)') }}) as first_departure,
        format_datetime('%H:%M', {{ as_mst('max(h.last_departure_ts)') }}) as last_departure,
        round(timestamp_diff(max(h.last_departure_ts), min(h.first_departure_ts), minute) / 60, 1) as span_hours,
        round(120 / nullif(sum(if(h.hour_mst between 7 and 8, h.n_departures, 0)), 0), 1) as headway_am_peak_min,
        round(360 / nullif(sum(if(h.hour_mst between 9 and 14, h.n_departures, 0)), 0), 1) as headway_midday_min,
        round(180 / nullif(sum(if(h.hour_mst between 15 and 17, h.n_departures, 0)), 0), 1) as headway_pm_peak_min,
        round(180 / nullif(sum(if(h.hour_mst between 18 and 20, h.n_departures, 0)), 0), 1) as headway_evening_min
    from trunk_hours as h
    group by 1, 2, 3, 4, 5
)

select
    p.route_id,
    r.route_name,
    r.route_long_name,
    p.direction_id,
    p.day_type,
    p.sample_date,
    p.busiest_stop_id,
    p.n_departures_busiest_stop,
    p.first_departure,
    p.last_departure,
    p.span_hours,
    p.headway_am_peak_min,
    p.headway_midday_min,
    p.headway_pm_peak_min,
    p.headway_evening_min,
    f.min_departures_per_3h,
    f.min_departures_per_3h >= 12 as is_frequent_day,
    rf.is_frequent_route,
    current_timestamp() as build_run_at
from per_direction as p
join frequency as f
    using (day_type, route_id, direction_id)
join route_flags as rf
    using (route_id)
left join {{ ref('dim_route') }} as r
    on r.route_id = p.route_id
    and r.is_latest_version
