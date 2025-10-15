{{ config(materialized='view') }}

with ranked_stops as (
    select
        stop_id,
        stop_name,
        stop_lat,
        stop_lon,
        {{ make_point('stop_lon', 'stop_lat') }} as geom,
        {{ safe_int('wheelchair_boarding') }} as wheelchair_boarding,
        row_number() over (
            partition by stop_id
            order by stop_name, stop_lat, stop_lon
        ) as stop_rank
    from {{ source('raw', 'raw_gtfs_stops') }}
)

select
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    geom,
    wheelchair_boarding
from ranked_stops
where stop_rank = 1
