{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'window_date_utc', 'data_type': 'date'},
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Realtime coverage per 15-minute window: how many distinct vehicle-feed updates the stream
recorded. RTD publishes about every 30 seconds (30 a window); fewer than 24, or none, marks the
window unhealthy, whether the poller or the feed was down. Marts use it so trips that ran during
an outage aren't reported as missed. Raw reports expire after 90 days, so full refresh is
disabled; nightly runs replace the last stream_health_days UTC dates, today's up to now.
#}
{% set days = var('stream_health_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('stream_health_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set first_ts = "timestamp(" ~ first ~ ")" %}

with updates as (
    select
        timestamp_seconds(div(unix_seconds(feed_ts_utc), 900) * 900) as window_start_utc,
        count(distinct feed_ts_utc) as n_feed_updates
    from {{ ref('stg_rt_vehicle_positions') }}
    where feed_ts_utc >= {{ first_ts }}
    group by 1
),
windows as (
    select window_start_utc
    from unnest(generate_timestamp_array(
        {{ first_ts }}, timestamp_sub(current_timestamp(), interval 15 minute), interval 15 minute
    )) as window_start_utc
)

select
    cast(w.window_start_utc as date) as window_date_utc,
    w.window_start_utc,
    coalesce(u.n_feed_updates, 0) as n_feed_updates,
    coalesce(u.n_feed_updates, 0) >= 24 as is_healthy
from windows as w
left join updates as u
    on u.window_start_utc = w.window_start_utc
