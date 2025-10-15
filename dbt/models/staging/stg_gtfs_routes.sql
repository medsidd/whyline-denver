{{ config(materialized='view') }}

with deduped as (
    select
        route_id,
        coalesce(nullif(route_short_name, ''), route_long_name) as route_name,
        route_long_name,
        route_type,
        route_desc,
        {{ 'TRUE' if execute else 'TRUE' }} as is_active,
        row_number() over (
            partition by route_id
            order by route_long_name, route_desc, route_short_name
        ) as route_rank
    from {{ source('raw', 'raw_gtfs_routes') }}
)

select
    route_id,
    route_name,
    route_long_name,
    route_type,
    route_desc,
    is_active
from deduped
where route_rank = 1
