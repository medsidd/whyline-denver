{{ config(materialized='table', meta={"allow_in_app": true}) }}

SELECT
    stop_id,
    stop_name,
    stop_lat AS lat,
    stop_lon AS lon
FROM {{ ref('stg_gtfs_stops') }}
