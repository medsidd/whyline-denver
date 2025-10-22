{{ config(materialized='view') }}

select
    feed_date_mst,
    event_rows,
    trips_observed,
    routes_observed,
    current_timestamp() as build_run_at
from {{ ref('stg_rt_events_daily_stats') }}
