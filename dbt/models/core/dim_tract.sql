{# Type 1: latest tract boundaries #}
select
    farm_fingerprint(geoid) as tract_key,
    geoid,
    name,
    aland_m2,
    awater_m2,
    geom
from {{ ref('stg_denver_tracts') }}
union all
select
    -1, cast(null as string), 'Unknown tract', cast(null as numeric), cast(null as numeric),
    cast(null as geography)
