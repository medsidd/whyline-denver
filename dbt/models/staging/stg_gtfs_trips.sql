{{ config(materialized='view') }}

{#
Every GTFS extract, one row per trip within each; dim_trip derives Type 2 versions.
is_valid: direction_id must be 0 or 1; it holds shape ids when the positional CSV load
shifted columns (2025-12-09 to 2026-01-04).
#}
select
    _extract_date,
    trip_id,
    route_id,
    service_id,
    direction_id,
    shape_id,
    trip_headsign,
    coalesce(direction_id in (0, 1), direction_id is null) as is_valid
from {{ source('raw', 'raw_gtfs_trips') }}
qualify row_number() over (partition by _extract_date, trip_id order by is_valid desc, service_id) = 1
