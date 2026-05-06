{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "dim"}
) }}

select
    route_id,
    route_name,
    route_long_name,
    route_type,
    route_desc
from {{ ref('stg_gtfs_routes') }}
