{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
Is service worse where the state and city prioritise? For Denver stops grouped by their block
group's Colorado EnviroScreen disproportionately impacted status and by Denver's DOTI equity
group (1 = highest need), over the last equity_window_days service dates: scheduled departures
per stop per day, on-time share, excess wait at frequent stops, and the share of visits arriving
with standing room only or worse. Missed trips are trip-level and not split here. Published with
release R2.
#}
{% set window_days = var('equity_window_days', 28) %}
{% set since = "date_sub(current_date('America/Denver'), interval " ~ window_days ~ " day)" %}
{% set until = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with stop_groups as (
    select sb.stop_id, 'disproportionately_impacted' as group_type,
        if(bg.is_disproportionately_impacted, 'impacted', 'not_impacted') as group_value
    from {{ ref('bridge_stop_block_group') }} as sb
    join {{ ref('dim_block_group') }} as bg on bg.block_group_key = sb.block_group_key
    union all
    select sb.stop_id, 'doti_equity_group', cast(bg.doti_equity_group_rank as string)
    from {{ ref('bridge_stop_block_group') }} as sb
    join {{ ref('dim_block_group') }} as bg on bg.block_group_key = sb.block_group_key
    where bg.doti_equity_group_rank is not null
),
departures as (
    select stop_id, count(*) / count(distinct service_date_mst) as departures_per_day
    from {{ ref('fct_scheduled_stop_time') }}
    where service_date_mst between {{ since }} and {{ until }}
    group by 1
),
headways as (
    select
        stop_id,
        if(scheduled_headway_sec between 1 and 900, observed_headway_sec, null) as h,
        if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, scheduled_headway_sec, null) as s,
        if(delay_sec is null, null,
            if(delay_sec > -{{ var('on_time_early_sec', 60) }} and delay_sec <= {{ var('on_time_late_sec', 300) }}, 1, 0)) as on_time
    from {{ ref('fct_stop_headway') }}
    where service_date between {{ since }} and {{ until }}
),
crowding as (
    select stop_id, max_level
    from {{ ref('fct_trip_occupancy') }}
    where service_date between {{ since }} and {{ until }} and max_level is not null
),
by_group as (
    select g.group_type, g.group_value, count(distinct g.stop_id) as n_stops,
        round(avg(d.departures_per_day), 1) as avg_departures_per_stop_day
    from stop_groups as g
    left join departures as d using (stop_id)
    group by 1, 2
),
wait as (
    select
        g.group_type,
        g.group_value,
        avg(h.on_time) as pct_on_time,
        safe_divide(sum(h.h * h.h), 2 * sum(h.h)) - safe_divide(sum(h.s * h.s), 2 * sum(h.s)) as excess_wait_sec
    from headways as h
    join stop_groups as g using (stop_id)
    group by 1, 2
),
crowd as (
    select g.group_type, g.group_value, avg(if(c.max_level >= 3, 1, 0)) as pct_visits_standing_or_worse
    from crowding as c
    join stop_groups as g using (stop_id)
    group by 1, 2
)

select
    b.group_type,
    b.group_value,
    b.n_stops,
    b.avg_departures_per_stop_day,
    w.pct_on_time,
    w.excess_wait_sec,
    c.pct_visits_standing_or_worse,
    current_timestamp() as build_run_at
from by_group as b
left join wait as w using (group_type, group_value)
left join crowd as c using (group_type, group_value)
