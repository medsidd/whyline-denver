{{ config(
    materialized='incremental',
    unique_key='transit_event_id',
    on_schema_change='fail',
    partition_by={
        'field': 'service_date_mst',
        'data_type': 'date',
        'granularity': 'day'
    },
    cluster_by=['route_id', 'stop_id'],
    meta={"allow_in_app": false, "layer": "fct"}
) }}

{% set lookback_days = var('rt_events_lookback_days', 45) %}
{% set incremental_days = 3 %}

select
    to_hex(sha256(concat(
        cast(feed_ts_utc as string),
        '|', cast(trip_id as string),
        '|', coalesce(cast(stop_id as string), '__null__')
    )))                 as transit_event_id,
    feed_ts_utc,
    route_id,
    trip_id,
    stop_id,
    direction_id,
    service_date_mst,
    event_hour_mst,
    event_ts_utc,
    delay_sec,
    delay_sec_raw,
    is_on_time
from {{ ref('int_rt_events_resolved') }}
{% if is_incremental() %}
where service_date_mst >= date_sub(current_date('America/Denver'), interval {{ incremental_days }} day)
{% else %}
where service_date_mst >= date_sub(current_date('America/Denver'), interval {{ lookback_days }} day)
{% endif %}
