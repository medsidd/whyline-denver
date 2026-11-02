{{ config(materialized='table', meta={"allow_in_app": true}) }}

{#
Scheduled service near each tract on the sample weekday. A stop's departures are shared among the
tracts within 804.672 m by population (bridge_stop_tract weights sum to 1 per stop), so tract
totals add up to the network total. Frequent stops have at least 4 departures in every hour from
9:00 to 14:59.
#}
with weekday_sample as (
    select sample_date
    from ({{ schedule_sample_dates() }})
    where day_type = 'weekday'
),
stop_hours as (
    select
        s.stop_id,
        {{ hour_mst('s.sched_departure_ts_mst') }} as hour_mst,
        count(*) as n_departures
    from {{ ref('fct_scheduled_stop_time') }} as s
    join weekday_sample as d
        on s.service_date_mst = d.sample_date
    where
        s.service_date_mst between current_date('America/Denver')
        and date_add(current_date('America/Denver'), interval 13 day)
    group by 1, 2
),
stops as (
    select
        stop_id,
        sum(n_departures) as n_departures,
        -- Hours with no departure make the stop infrequent.
        count(distinct if(hour_mst between 9 and 14 and n_departures >= 4, hour_mst, null)) = 6 as is_frequent_stop
    from stop_hours
    group by 1
)

select
    b.geoid,
    any_value(b.tract_pop_total) as tract_pop_total,
    (select w.sample_date from weekday_sample as w) as sample_date,
    count(distinct b.stop_id) as n_stops_nearby,
    count(distinct if(s.is_frequent_stop, b.stop_id, null)) as n_frequent_stops_nearby,
    round(sum(coalesce(s.n_departures, 0) * b.weighting_factor), 1) as weekday_departures_share,
    round(
        safe_divide(sum(coalesce(s.n_departures, 0) * b.weighting_factor), any_value(b.tract_pop_total) / 1000),
        1
    ) as weekday_departures_per_1000_residents,
    current_timestamp() as build_run_at
from {{ ref('bridge_stop_tract') }} as b
left join stops as s
    using (stop_id)
group by 1
