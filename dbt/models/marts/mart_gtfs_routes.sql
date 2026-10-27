{{ config(materialized='table', meta={"allow_in_app": true}) }}

{# Last known version of every route ever published, so historical route_ids keep their names #}
select
    route_id,
    route_name,
    route_long_name,
    route_type
from {{ ref('dim_route') }}
where is_latest_version
