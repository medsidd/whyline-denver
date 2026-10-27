{#
Many-to-many between current stops and the census tracts within 804.672 m (half a mile, a
standard walkable catchment). weighting_factor is each tract's share of the population
around the stop (latest ACS vintage, tracts with population only); it sums to 1 per stop.
#}
with stops as (
    select stop_key, stop_id, geom
    from {{ ref('dim_stop') }}
    where is_current
),
tracts as (
    select tract_key, geoid, geom
    from {{ ref('dim_tract') }}
    where tract_key != -1
),
latest_acs as (
    select geoid, acs_year, pop_total
    from {{ ref('fct_tract_demographics') }}
    qualify row_number() over (partition by geoid order by acs_year desc) = 1
),
near as (
    select
        s.stop_key,
        s.stop_id,
        t.tract_key,
        t.geoid
    from stops as s
    join tracts as t
        on st_dwithin(s.geom, t.geom, 804.672)
)

select
    n.stop_key,
    n.stop_id,
    n.tract_key,
    n.geoid,
    a.acs_year,
    a.pop_total as tract_pop_total,
    a.pop_total / sum(a.pop_total) over (partition by n.stop_key) as weighting_factor
from near as n
join latest_acs as a
    using (geoid)
where a.pop_total > 0
