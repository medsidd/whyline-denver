{{ config(materialized='view', meta={"allow_in_app": false}) }}
select route_id, route_name, route_long_name, route_type
from {{ ref('dim_route') }}
