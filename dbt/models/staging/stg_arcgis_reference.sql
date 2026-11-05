{{ config(materialized='view') }}

{#
Silver: ArcGIS reference layers (street safety, equity) from each layer's latest extract, with
geometry parsed. Layers refresh weekly and independently, so the latest extract is per layer;
the 60-day bound keeps the partition scan small. Core models pick their layer and fields.
#}
{% if target.type == 'bigquery' %}
    {% set geom_expression = "ST_GEOGFROMGEOJSON(geometry_geojson, make_valid => true)" %}
{% else %}
    {% set geom_expression = "ST_GEOGFROMGEOJSON(geometry_geojson)" %}
{% endif %}

select
    layer,
    object_id,
    properties_json,
    {{ geom_expression }} as geom,
    _extract_date
from {{ source('raw', 'raw_arcgis_reference') }}
where _extract_date >= date_sub(current_date(), interval 60 day)
qualify _extract_date = max(_extract_date) over (partition by layer)
    and row_number() over (partition by layer, object_id order by _ingested_at desc) = 1
