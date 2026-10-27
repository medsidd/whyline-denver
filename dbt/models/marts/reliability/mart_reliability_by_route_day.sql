{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    unique_key=['route_id', 'service_date_mst', 'precip_bin', 'snow_day'],
    partition_by={"field": "service_date_mst", "data_type": "date"},
    cluster_by=["route_id"],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": true}
) }}

{# Realtime runs pass route_day_window_days=2; nightly runs rebuild 30 days so late weather lands #}
{% set window_days = var('route_day_window_days', var('weather_lookback_days', 30)) %}

with e as (
    select
        route_id,
        service_date_mst,
        delay_sec,
        delay_sec_raw
    from {{ ref('fct_trip_observation') }}
    -- Unassigned events remain in the fact (route_key -1) but cannot contribute to route metrics.
    where route_id is not null
    {% if is_incremental() %}
        and service_date_mst >= date_sub(current_date("America/Denver"), interval {{ window_days }} day)
    {% endif %}
),
w as (
    select
        weather_date as service_date_mst,
        precip_bin,
        snow_day
    from {{ ref('fct_weather_daily') }}
    where station = '{{ var("weather_station", "USW00003017") }}'
),
agg as (
    select
        e.route_id,
        e.service_date_mst,
        coalesce(w.precip_bin, 'unknown') as precip_bin,
        w.snow_day as snow_day,
        count(*) as n_events,
        countif(delay_sec_raw is not null) as n_reported_events,
        avg(case when abs(delay_sec) <= {{ var('on_time_sec', 300) }} then 1 else 0 end) as pct_on_time,
        avg(delay_sec) as mean_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(50)] as median_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(90)] as p90_delay_sec,
        current_timestamp() as build_run_at
    from e
    left join w
        using (service_date_mst)
    group by
        route_id,
        service_date_mst,
        precip_bin,
        snow_day
)

select
    agg.*,
    r.route_name,
    r.route_long_name
from agg
left join {{ ref('dim_route') }} as r
    on r.route_id = agg.route_id
    and r.is_latest_version
