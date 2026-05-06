{{ config(materialized='view', meta={"allow_in_app": false}) }}
select stop_id, stop_name, lat, lon
from {{ ref('dim_stop') }}
