{{ config(materialized='view') }}

{#
Every GTFS extract, one row per route within each; dim_route derives Type 2 versions.
is_valid: route colors must be 6-digit hex, which fails when the positional CSV load
shifted columns (e.g. 2025-12-15, 2026-05/06 loads). route_type is often empty in
older extracts, so it is not part of the check.
#}
select
    _extract_date,
    route_id,
    coalesce(nullif(route_short_name, ''), route_long_name) as route_name,
    route_long_name,
    route_type,
    route_desc,
    coalesce(
        regexp_contains(coalesce(route_color, ''), r'^([0-9A-Fa-f]{6})?$')
        and regexp_contains(coalesce(route_text_color, ''), r'^([0-9A-Fa-f]{6})?$'),
        false
    ) as is_valid
from {{ source('raw', 'raw_gtfs_routes') }}
qualify row_number() over (
    partition by _extract_date, route_id
    order by is_valid desc, route_long_name, route_desc, route_short_name
) = 1
