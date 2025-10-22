{{ config(materialized='table', meta={"allow_in_app": true}) }}

with base as (
    select
        route_id,
        precip_bin,
        pct_on_time
    from {{ ref('mart_reliability_by_route_day') }}
),
avgd as (
    select
        route_id,
        precip_bin,
        avg(pct_on_time) as pct_on_time_avg
    from base
    group by
        route_id,
        precip_bin
),
norm as (
    select
        a.route_id,
        a.precip_bin,
        a.pct_on_time_avg,
        n.pct_on_time_avg as pct_on_time_normal
    from avgd as a
    left join avgd as n
        on a.route_id = n.route_id
        and n.precip_bin = 'none'
)

select
    route_id,
    precip_bin,
    pct_on_time_avg,
    pct_on_time_normal,
    pct_on_time_avg - pct_on_time_normal as delta_pct_on_time,
    current_timestamp() as build_run_at
from norm
