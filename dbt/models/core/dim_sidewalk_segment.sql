{# Type 1: latest sidewalk inventory #}
select
    farm_fingerprint(sidewalk_id) as sidewalk_key,
    sidewalk_id,
    class,
    status,
    material,
    year_built,
    length_m,
    geom,
    centroid
from {{ ref('stg_sidewalks') }}
union all
select
    -1, cast(null as string), cast(null as string), cast(null as string), cast(null as string),
    cast(null as string), cast(null as float64), cast(null as geography), cast(null as geography)
