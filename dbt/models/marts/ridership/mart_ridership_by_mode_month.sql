{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
RTD ridership and service by mode and month from the National Transit Database: boardings
(unlinked trips, so a transfer counts twice), revenue hours and miles, boardings per revenue
hour, and the change from the same month a year earlier. NTD runs about two months behind.
#}
with by_mode as (
    select
        month,
        mode,
        any_value(mode_group) as mode_group,
        sum(upt) as boardings,
        sum(vrh) as revenue_hours,
        sum(vrm) as revenue_miles,
        sum(voms) as peak_vehicles
    from {{ ref('fct_ntd_service_month') }}
    group by 1, 2
)

select
    b.month,
    b.mode,
    case b.mode
        when 'MB' then 'Bus'
        when 'LR' then 'Light rail'
        when 'CR' then 'Commuter rail'
        when 'DR' then 'Demand response'
        when 'VP' then 'Vanpool'
        else b.mode
    end as mode_name,
    b.mode_group,
    b.boardings,
    b.revenue_hours,
    b.revenue_miles,
    b.peak_vehicles,
    round(safe_divide(b.boardings, b.revenue_hours), 2) as boardings_per_revenue_hour,
    prior.boardings as boardings_year_earlier,
    round(safe_divide(b.boardings, prior.boardings) - 1, 4) as boardings_yoy_change,
    current_timestamp() as build_run_at
from by_mode as b
-- A join, not lag(12), so a missing month can't shift the comparison.
left join by_mode as prior
    on prior.mode = b.mode
    and prior.month = date_sub(b.month, interval 12 month)
