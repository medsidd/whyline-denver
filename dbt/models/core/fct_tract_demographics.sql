{# Grain: one tract x ACS vintage (periodic snapshot) #}
select
    a.geoid,
    coalesce(t.tract_key, -1) as tract_key,
    a.year as acs_year,
    a.name,
    a.pop_total,
    a.hh_total,
    a.hh_no_vehicle,
    a.workers_total,
    a.workers_transit,
    a.persons_poverty,
    a.pct_hh_no_vehicle,
    a.pct_transit_commute,
    a.pct_poverty
from {{ ref('stg_acs_geo') }} as a
left join {{ ref('dim_tract') }} as t
    on t.geoid = a.geoid
