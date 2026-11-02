{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
Why do WhyLine's numbers differ from RTD's? RTD's reported monthly on-time performance beside
WhyLine's measured share for the same month and service: all bus, light rail, the A, B and G
commuter lines, and the N Line. RTD measures at timepoints with its own rules; WhyLine at every
stop it times, 1 minute early to 5 minutes late. Months only overlap once WhyLine has measured
them (from 2026-10-28) and RTD has published them (about two months later). Local, Regional
and Regional BRT need RTD's route classification and aren't split. Published with release R3.
#}
with reported as (
    select
        report_month,
        service,
        round(max(if(metric = 'otp_month', value_pct, null)) / 100, 4) as rtd_pct_on_time,
        round(max(if(metric = 'service_availability', value_pct, null)) / 100, 4) as rtd_service_availability
    from {{ ref('fct_rtd_reported_performance') }}
    where service in ('all_bus', 'light_rail', 'commuter_rail_abg', 'commuter_rail_n')
    group by 1, 2
),
measured as (
    select
        date_trunc(v.service_date, month) as report_month,
        case
            when r.route_type = '3' then 'all_bus'
            when r.route_type = '0' then 'light_rail'
            when v.route_id = '117N' then 'commuter_rail_n'
            when r.route_type = '2' then 'commuter_rail_abg'
        end as service,
        count(*) as n_visits_measured,
        count(distinct v.service_date) as n_days_measured,
        avg(if(v.delay_sec between -{{ var('on_time_early_sec', 60) }} and {{ var('on_time_late_sec', 300) }}, 1, 0))
            as whyline_pct_on_time
    from {{ ref('fct_stop_visit') }} as v
    join {{ ref('dim_route') }} as r
        on r.route_id = v.route_id
        and r.is_latest_version
    where v.delay_sec is not null
    group by 1, 2
)

select
    coalesce(r.report_month, m.report_month) as report_month,
    coalesce(r.service, m.service) as service,
    r.rtd_pct_on_time,
    r.rtd_service_availability,
    round(m.whyline_pct_on_time, 4) as whyline_pct_on_time,
    round(m.whyline_pct_on_time - r.rtd_pct_on_time, 4) as difference_pct_on_time,
    m.n_visits_measured,
    m.n_days_measured,
    current_timestamp() as build_run_at
from reported as r
full join measured as m
    on m.report_month = r.report_month
    and m.service = r.service
where coalesce(r.service, m.service) is not null
