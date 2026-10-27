{{ config(materialized='view') }}

{# Every GTFS extract, one row per stop within each; dim_stop derives Type 2 versions #}
select
    _extract_date,
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    {{ make_point('stop_lon', 'stop_lat') }} as geom,
    {{ safe_int('wheelchair_boarding') }} as wheelchair_boarding
from {{ source('raw', 'raw_gtfs_stops') }}
qualify row_number() over (
    partition by _extract_date, stop_id
    order by stop_name, stop_lat, stop_lon
) = 1
