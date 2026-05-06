{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "dim"}
) }}

select
    stop_id,
    stop_name,
    stop_lat as lat,
    stop_lon as lon,
    wheelchair_boarding
from {{ ref('stg_gtfs_stops') }}
