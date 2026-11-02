{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='alert_id',
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Grain: one RTD service alert, kept permanently (raw snapshots expire after 90 days). first_seen
and last_seen bound when the alert was in the feed; cause, effect and text are the latest seen.
Nightly runs merge the last alerts_lookback_days of snapshots, keeping the earliest first_seen.
#}
{% set lookback = var('alerts_lookback_days', 3) %}

with batch as (
    select
        alert_id,
        min(feed_ts_utc) as first_seen_ts,
        max(feed_ts_utc) as last_seen_ts,
        array_agg(
            struct(cause, effect, header_text, description_text, url)
            order by feed_ts_utc desc limit 1
        )[offset(0)] as latest
    from {{ ref('stg_rt_alerts') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {{ lookback }} day)
    group by 1
)

select
    b.alert_id,
    {% if is_incremental() %}
    least(b.first_seen_ts, coalesce(f.first_seen_ts, b.first_seen_ts)) as first_seen_ts,
    {% else %}
    b.first_seen_ts,
    {% endif %}
    b.last_seen_ts,
    b.latest.cause,
    b.latest.effect,
    b.latest.header_text,
    b.latest.description_text,
    b.latest.url
from batch as b
{% if is_incremental() %}
left join {{ this }} as f
    on f.alert_id = b.alert_id
{% endif %}
