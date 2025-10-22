{{ config(materialized='view') }}

{% if target.type == 'bigquery' %}
    {% set geom_expression = "ST_GEOGFROMGEOJSON(geometry_geojson, make_valid => true)" %}
{% else %}
    {% set geom_expression = "ST_GEOGFROMGEOJSON(geometry_geojson)" %}
{% endif %}

with ranked as (
    select
        geoid,
        name,
        aland_m2,
        awater_m2,
        geometry_geojson,
        _ingested_at,
        row_number() over (
            partition by geoid
            order by _ingested_at desc
        ) as record_rank
    from {{ source('raw', 'raw_denver_tracts') }}
)

select
    geoid,
    name,
    aland_m2,
    awater_m2,
    {{ geom_expression }} as geom
from ranked
where record_rank = 1
