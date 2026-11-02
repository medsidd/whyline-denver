{{ config(
    materialized='table',
    cluster_by=['stop_id'],
    meta={"allow_in_app": false}
) }}

{#
How long riders actually wait at each stop, by route, direction, day type and period, over the
last wait_window_days complete service dates. With riders arriving at random, the average wait
is E[H^2] / 2E[H] over the headways H between vehicles; excess wait is that minus the same over
the scheduled headways. Frequent groups (scheduled every 15 minutes or better on average) are
read by excess wait; infrequent ones by on-time share, since riders time their arrival.
Published after the stop-visit review.
#}
{% set window_days = var('wait_window_days', 28) %}

with headways as (
    -- h and s: observed and scheduled headways, kept only where both are known.
    select
        *,
        if(scheduled_headway_sec > 0, observed_headway_sec, null) as h,
        if(observed_headway_sec is not null and scheduled_headway_sec > 0, scheduled_headway_sec, null) as s
    from {{ ref('fct_stop_headway') }}
    where service_date between date_sub(current_date('America/Denver'), interval {{ window_days }} day)
        and date_sub(current_date('America/Denver'), interval 1 day)
),
grouped as (
    select
        stop_id,
        route_id,
        direction_id,
        day_type,
        period,
        count(distinct service_date) as n_days,
        count(*) as n_visits,
        count(h) as n_headways,
        avg(s) as avg_scheduled_headway_sec,
        safe_divide(sum(h * h), 2 * sum(h)) as expected_wait_sec,
        safe_divide(sum(s * s), 2 * sum(s)) as scheduled_wait_sec,
        avg(if(h is null, null, if(h < 0.25 * s, 1, 0))) as pct_bunched,
        avg(if(h is null, null, if(h > 1.5 * s, 1, 0))) as pct_gap,
        avg(if(
            delay_sec is null, null,
            if(delay_sec between -{{ var('on_time_early_sec', 60) }} and {{ var('on_time_late_sec', 300) }}, 1, 0)
        )) as pct_on_time,
        approx_quantiles(delay_sec, 10)[offset(9)] as p90_delay_sec
    from headways
    group by 1, 2, 3, 4, 5
)

select
    g.stop_id,
    st.stop_name,
    st.lat,
    st.lon,
    g.route_id,
    g.direction_id,
    g.day_type,
    g.period,
    if(g.avg_scheduled_headway_sec <= 900, 'frequent', 'infrequent') as service_class,
    g.n_days,
    g.n_visits,
    g.n_headways,
    g.avg_scheduled_headway_sec,
    g.expected_wait_sec,
    g.scheduled_wait_sec,
    g.expected_wait_sec - g.scheduled_wait_sec as excess_wait_sec,
    g.pct_bunched,
    g.pct_gap,
    g.pct_on_time,
    g.p90_delay_sec,
    current_timestamp() as build_run_at
from grouped as g
left join {{ ref('dim_stop') }} as st
    on st.stop_id = g.stop_id
    and st.is_current
