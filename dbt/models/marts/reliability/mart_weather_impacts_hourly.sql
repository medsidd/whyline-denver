{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
Reliability by the weather in the hour the vehicle reached the stop, per route, over the last
weather_hourly_window_days service dates: precipitation band, whether snow was falling, and
temperature band. delta_pct_on_time compares each level with the route's dry, not-snowing or
0-30 C baseline. Hourly weather is modelled at the airport, and association is not causation.
Published after the stop-visit review.
#}
{% set window_days = var('weather_hourly_window_days', 90) %}

with visits as (
    select
        v.route_id,
        if(v.delay_sec between -{{ var('on_time_early_sec', 60) }} and {{ var('on_time_late_sec', 300) }}, 1, 0) as on_time,
        v.delay_sec,
        w.precip_mm,
        w.snowfall_mm,
        w.temp_c
    from {{ ref('fct_stop_visit') }} as v
    join {{ ref('fct_weather_hourly') }} as w
        on w.ts_utc = timestamp_trunc(v.arrival_ts_utc, hour)
        and w.station = '{{ var("weather_station") }}'
    where
        v.service_date >= date_sub(current_date('America/Denver'), interval {{ window_days }} day)
        and v.delay_sec is not null
        and v.route_id is not null
),
levels as (
    select route_id, on_time, delay_sec, 'precipitation' as factor,
        case
            when precip_mm < 0.1 then 'none'
            when precip_mm < 1 then 'light'
            when precip_mm < 4 then 'moderate'
            else 'heavy'
        end as level
    from visits
    where precip_mm is not null
    union all
    select route_id, on_time, delay_sec, 'snowfall', if(snowfall_mm > 0, 'snowing', 'not_snowing')
    from visits
    where snowfall_mm is not null
    union all
    select route_id, on_time, delay_sec, 'temperature',
        case
            when temp_c < -10 then 'below_-10'
            when temp_c < 0 then '-10_to_0'
            when temp_c < 30 then '0_to_30'
            else '30_plus'
        end
    from visits
    where temp_c is not null
),
grouped as (
    select
        route_id,
        factor,
        level,
        count(*) as n_visits,
        avg(on_time) as pct_on_time,
        avg(delay_sec) as mean_delay_sec,
        approx_quantiles(delay_sec, 10)[offset(9)] as p90_delay_sec
    from levels
    group by 1, 2, 3
)

select
    *,
    pct_on_time - max(if(level in ('none', 'not_snowing', '0_to_30'), pct_on_time, null))
        over (partition by route_id, factor) as delta_pct_on_time,
    current_timestamp() as build_run_at
from grouped
