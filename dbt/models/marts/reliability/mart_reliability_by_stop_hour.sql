{{ config(materialized='view', meta={"allow_in_app": false}) }}
select
    stop_id, service_date_mst, event_hour_mst,
    n_events, pct_on_time, mean_delay_sec, p90_delay_sec,
    route_id_mode, headway_adherence_rate,
    obs_headway_sec_p50, obs_headway_sec_p90, build_run_at
from {{ ref('agg_reliability_by_stop_hour') }}
