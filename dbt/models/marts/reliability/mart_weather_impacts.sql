{{ config(materialized='view', meta={"allow_in_app": false}) }}
select route_id, precip_bin, pct_on_time_avg, pct_on_time_normal, delta_pct_on_time, build_run_at
from {{ ref('agg_weather_impacts_by_route') }}
