{{ config(materialized='view') }}

{# Every GTFS extract, one row per route within each; dim_route derives Type 2 versions #}
select
    _extract_date,
    route_id,
    coalesce(nullif(route_short_name, ''), route_long_name) as route_name,
    route_long_name,
    route_type,
    route_desc
from {{ source('raw', 'raw_gtfs_routes') }}
qualify row_number() over (
    partition by _extract_date, route_id
    order by route_long_name, route_desc, route_short_name
) = 1
