{{ config(materialized='view') }}

{# Limit historical scan to reduce BigQuery costs - matches rt_events_lookback_days #}
{% set lookback_days = var('rt_events_lookback_days', 45) %}

with base as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        event_ts_utc
    from {{ ref('int_rt_events_resolved') }}
    where event_ts_utc is not null
        and service_date_mst >= date_sub(current_date("America/Denver"), interval {{ lookback_days }} day)
),
deduped as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        event_ts_utc
    from (
        select
            *,
            row_number() over (
                partition by route_id, direction_id, stop_id, service_date_mst, event_ts_utc
                order by event_ts_utc
            ) as event_rank
        from base
    )
    where event_rank = 1
)

select
    route_id,
    direction_id,
    stop_id,
    service_date_mst,
    event_ts_utc,
    timestamp_diff(
        event_ts_utc,
        lag(event_ts_utc) over (
            partition by route_id, direction_id, stop_id, service_date_mst
            order by event_ts_utc
        ),
        second
    ) as obs_headway_sec
from deduped
