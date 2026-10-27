{{ config(materialized='view') }}

{#
Every GTFS extract, one row per stop within each; dim_stop derives Type 2 versions.
is_valid: GTFS-format check. The loader maps CSV columns by position, so a reordered
source file loads into the wrong columns; consumers use valid rows only.
#}
select
    _extract_date,
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    {{ make_point('stop_lon', 'stop_lat') }} as geom,
    {{ safe_int('wheelchair_boarding') }} as wheelchair_boarding,
    coalesce(stop_lat between -90 and 90 and stop_lon between -180 and 180, false) as is_valid
from {{ source('raw', 'raw_gtfs_stops') }}
qualify row_number() over (
    partition by _extract_date, stop_id
    order by is_valid desc, stop_name, stop_lat, stop_lon
) = 1
