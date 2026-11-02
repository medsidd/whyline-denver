{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='alert_entity_period_key',
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Grain: one alert x informed entity (route, direction, stop, trip) x active period, kept
permanently. first_seen and last_seen say in which snapshots that combination appeared, so a
period RTD later edited stays as history; marts use the rows from the alert's last snapshot. An
alert without periods has one row per entity with NULL start and end: active while in the feed.
#}
{% set lookback = var('alerts_lookback_days', 3) %}

with entities as (
    select distinct feed_ts_utc, alert_id, route_id, route_type, direction_id, stop_id, trip_id
    from {{ ref('stg_rt_alerts') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {{ lookback }} day)
),
periods as (
    select distinct feed_ts_utc, alert_id, active_start_utc, active_end_utc
    from {{ ref('stg_rt_alert_periods') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {{ lookback }} day)
),
batch as (
    select
        farm_fingerprint(concat(
            e.alert_id, '|', coalesce(e.route_id, ''), '|', coalesce(cast(e.direction_id as string), ''), '|',
            coalesce(e.stop_id, ''), '|', coalesce(e.trip_id, ''), '|',
            coalesce(cast(p.active_start_utc as string), ''), '|', coalesce(cast(p.active_end_utc as string), '')
        )) as alert_entity_period_key,
        e.alert_id,
        e.route_id,
        e.route_type,
        e.direction_id,
        e.stop_id,
        e.trip_id,
        p.active_start_utc,
        p.active_end_utc,
        min(e.feed_ts_utc) as first_seen_ts,
        max(e.feed_ts_utc) as last_seen_ts
    from entities as e
    left join periods as p
        on p.feed_ts_utc = e.feed_ts_utc
        and p.alert_id = e.alert_id
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
)

select
    b.alert_entity_period_key,
    b.alert_id,
    b.route_id,
    b.route_type,
    b.direction_id,
    b.stop_id,
    b.trip_id,
    b.active_start_utc,
    b.active_end_utc,
    {% if is_incremental() %}
    least(b.first_seen_ts, coalesce(f.first_seen_ts, b.first_seen_ts)) as first_seen_ts,
    {% else %}
    b.first_seen_ts,
    {% endif %}
    b.last_seen_ts
from batch as b
{% if is_incremental() %}
left join {{ this }} as f
    on f.alert_entity_period_key = b.alert_entity_period_key
{% endif %}
