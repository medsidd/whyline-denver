{{ config(materialized='table', meta={"allow_in_app": true}) }}

SELECT
    route_id,
    route_name,
    route_long_name,
    route_type
FROM {{ ref('stg_gtfs_routes') }}
