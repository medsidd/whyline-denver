{{ config(materialized='table', meta={"allow_in_app": true}) }}

{# Last known version of every stop ever published, so historical stop_ids keep their names #}
select
    stop_id,
    stop_name,
    lat,
    lon
from {{ ref('dim_stop') }}
where is_latest_version
