{{ config(materialized='view', meta={"allow_in_app": false}) }}
select
    route_id, service_date_mst, precip_bin, snow_day,
    n_events, n_reported_events, pct_on_time,
    mean_delay_sec, median_delay_sec, p90_delay_sec, build_run_at
from {{ ref('agg_reliability_by_route_day') }}
