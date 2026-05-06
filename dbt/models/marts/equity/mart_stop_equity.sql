{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "mart"}
) }}

with stops as (
    select stop_id, geom
    from {{ ref('stg_gtfs_stops') }}
),

near as (
    select
        s.stop_id,
        t.geoid,
        t.pop_total,
        t.pct_hh_no_vehicle,
        t.pct_transit_commute,
        t.pct_poverty
    from stops as s
    join {{ ref('dim_census_tract') }} as t
        -- 804.672 m ≈ 0.5 miles; standard transit equity walkshed catchment distance
        on st_dwithin(s.geom, t.geom, 804.672)
    where t.pop_total > 0
),

norm as (
    select
        stop_id,
        sum(pop_total)                                              as pop_sum,
        sum(pct_hh_no_vehicle  * pop_total) / nullif(sum(pop_total), 0) as pct_hh_no_vehicle_w,
        sum(pct_transit_commute * pop_total) / nullif(sum(pop_total), 0) as pct_transit_commute_w,
        sum(pct_poverty        * pop_total) / nullif(sum(pop_total), 0) as pct_poverty_w
    from near
    group by stop_id
),

score as (
    select
        *,
        (pct_hh_no_vehicle_w + pct_transit_commute_w + pct_poverty_w) / 3.0 as vuln_raw
    from norm
),

joined as (
    select
        s.stop_id,
        n.pct_hh_no_vehicle_w,
        n.pct_transit_commute_w,
        n.pct_poverty_w,
        n.vuln_raw
    from stops as s
    left join score as n using (stop_id)
)

select
    stop_id,
    pct_hh_no_vehicle_w,
    pct_transit_commute_w,
    pct_poverty_w,
    cast(
        round(
            case
                when max(vuln_raw) over () = min(vuln_raw) over () then 100
                else
                    (vuln_raw - min(vuln_raw) over ()) /
                    nullif(max(vuln_raw) over () - min(vuln_raw) over (), 0) * 100
            end,
            1
        ) as float64
    )               as vuln_score_0_100,
    current_timestamp() as build_run_at
from joined
