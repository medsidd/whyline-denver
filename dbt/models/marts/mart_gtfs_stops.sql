{{ config(materialized='table', meta={"allow_in_app": true}) }}

SELECT
    stop_id,
    stop_name
FROM {{ ref('stg_gtfs_stops') }}
