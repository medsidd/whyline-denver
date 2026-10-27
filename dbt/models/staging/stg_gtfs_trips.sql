{{ config(materialized='view') }}

{# Every GTFS extract, one row per trip within each; dim_trip derives Type 2 versions #}
select
    _extract_date,
    trip_id,
    route_id,
    service_id,
    direction_id,
    shape_id,
    trip_headsign
from {{ source('raw', 'raw_gtfs_trips') }}
qualify row_number() over (partition by _extract_date, trip_id order by service_id) = 1
