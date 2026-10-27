{{ config(materialized='view') }}

{# Latest extract only, one row per segment #}
select
    sidewalk_id,
    class,
    status,
    material,
    year_built,
    length_m,
    st_makeline(
        st_geogpoint(cast(lon_start as float64), cast(lat_start as float64)),
        st_geogpoint(cast(lon_end as float64), cast(lat_end as float64))
    ) as geom,
    st_geogpoint(cast(centroid_lon as float64), cast(centroid_lat as float64)) as centroid
from {{ source('raw','raw_sidewalks') }}
where _extract_date = {{ latest_extract_date(source('raw','raw_sidewalks')) }}
qualify row_number() over (partition by sidewalk_id order by _ingested_at desc) = 1
