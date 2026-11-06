-- The route-day and stop-hour marts count the same stop visits, so on stop-visit days their
-- totals must match. Checks the last three service dates.
with route_day as (
    select service_date_mst, sum(n_events) as n_events
    from {{ ref('mart_reliability_by_route_day') }}
    where data_version is not null
      and service_date_mst >= date_sub(current_date('America/Denver'), interval 3 day)
    group by 1
),
stop_hour as (
    select service_date_mst, sum(n_events) as n_events
    from {{ ref('mart_reliability_by_stop_hour') }}
    where data_version is not null
      and service_date_mst >= date_sub(current_date('America/Denver'), interval 3 day)
    group by 1
)
select service_date_mst, r.n_events as route_day_events, s.n_events as stop_hour_events
from route_day as r
full join stop_hour as s using (service_date_mst)
where r.n_events is distinct from s.n_events
