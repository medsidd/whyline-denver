{{ config(
    materialized='table',
    meta={"allow_in_app": false, "layer": "mart"}
) }}

select
    stop_id,
    cast(
        round(100.0 * (1 - avg(pct_on_time)), 1) as float64
    )               as reliability_score_0_100,
    current_timestamp() as build_run_at
from {{ ref('agg_reliability_by_stop_hour') }}
where service_date_mst >= date_sub(current_date("America/Denver"), interval 35 day)
group by stop_id
