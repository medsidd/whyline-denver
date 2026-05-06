{{ config(
    materialized='table',
    meta={"allow_in_app": false, "layer": "dim"}
) }}

with tracts as (
    select
        regexp_replace(geoid, '^14000US', '') as geoid,
        name,
        aland_m2,
        geom
    from {{ ref('stg_denver_tracts') }}
    qualify row_number() over (partition by regexp_replace(geoid, '^14000US', '') order by geoid) = 1
),

acs as (
    select
        regexp_replace(geoid, '^14000US', '') as geoid,
        pop_total,
        pct_hh_no_vehicle,
        pct_transit_commute,
        pct_poverty
    from {{ ref('stg_acs_geo') }}
    where pop_total > 0
    qualify row_number() over (partition by regexp_replace(geoid, '^14000US', '') order by geoid) = 1
)

select
    t.geoid,
    t.name,
    t.aland_m2,
    t.geom,
    a.pct_hh_no_vehicle,
    a.pct_transit_commute,
    a.pct_poverty,
    a.pop_total
from tracts as t
left join acs as a using (geoid)
