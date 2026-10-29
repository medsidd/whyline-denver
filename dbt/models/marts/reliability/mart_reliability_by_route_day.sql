{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    unique_key=['route_id', 'service_date_mst', 'precip_bin', 'snow_day'],
    partition_by={"field": "service_date_mst", "data_type": "date"},
    cluster_by=["route_id"],
    on_schema_change='append_new_columns',
    full_refresh=false,
    meta={"allow_in_app": true}
) }}

{#
Observed stop visits (core.fct_stop_visit) per route and service date. On time follows RTD:
less than one minute early and no more than five minutes late; visits with an unknown delay are
excluded from the on-time share and the delay statistics instead of counting as on time.
pct_observed is the share of the day's scheduled stop events that have an observed visit:
canceled and unseen trips count against it, trips not in the schedule don't count, and the
current day's value rises as the day goes on. Backfilled (15-minute sample) visits stay out
until their calibration is published (publish_backfill). Partitions built before the cutover
keep the legacy sampled method; their data_version is NULL. Realtime runs pass
route_day_window_days=1 (yesterday and today, the dates fct_stop_visit still changes); nightly
runs rebuild 30 days so late weather lands. Full refreshes are disabled because pre-cutover
partitions can no longer be rebuilt; rebuild a longer span with a wider route_day_window_days.
#}
{% set window_days = var('route_day_window_days', var('weather_lookback_days', 30)) %}
{% set versions = "'stream_v1', 'backfill_v1'" if var('publish_backfill', false) else "'stream_v1'" %}

with e as (
    select
        route_id,
        service_date as service_date_mst,
        delay_sec,
        arrival_method,
        arrival_window_sec,
        within_30s,
        skipped,
        data_version
    from {{ ref('fct_stop_visit') }}
    -- Unassigned visits remain in the fact (route_key -1) but cannot contribute to route metrics.
    where route_id is not null
      and data_version in ({{ versions }})
    {% if is_incremental() %}
        and service_date >= date_sub(current_date("America/Denver"), interval {{ window_days }} day)
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
canceled as (
    select
        route_id,
        service_date as service_date_mst,
        countif(outcome = 'canceled') as n_canceled_trips
    from {{ ref('fct_trip_status') }}
    where route_id is not null
      and data_version in ({{ versions }})
    {% if is_incremental() %}
        and service_date >= date_sub(current_date("America/Denver"), interval {{ window_days }} day)
    {% endif %}
    group by route_id, service_date_mst
),
scheduled as (
    -- The schedule fact runs 30 days ahead, so the upper bound keeps the scan to the window.
    select
        route_id,
        service_date_mst,
        count(*) as n_scheduled
    from {{ ref('fct_scheduled_stop_time') }}
    where service_date_mst <= current_date("America/Denver")
    {% if is_incremental() %}
        and service_date_mst >= date_sub(current_date("America/Denver"), interval {{ window_days }} day)
    {% endif %}
    group by route_id, service_date_mst
),
agg as (
    select
        e.route_id,
        e.service_date_mst,
        coalesce(w.precip_bin, 'unknown') as precip_bin,
        w.snow_day as snow_day,
        countif(not skipped) as n_events,
        countif(delay_sec is not null) as n_reported_events,
        avg(
            case
                when delay_sec is null then null
                when delay_sec > -{{ var('on_time_early_sec', 60) }}
                    and delay_sec <= {{ var('on_time_late_sec', 300) }} then 1
                else 0
            end
        ) as pct_on_time,
        avg(delay_sec) as mean_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(50)] as median_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(90)] as p90_delay_sec,
        current_timestamp() as build_run_at,
        if(count(distinct data_version) > 1, 'mixed', any_value(data_version)) as data_version,
        countif(skipped) as n_skipped,
        safe_divide(
            countif(arrival_method like '%crossing%' or arrival_method = 'origin_departure'),
            countif(not skipped)
        ) as pct_shape_crossing,
        safe_divide(countif(arrival_method like '%prediction%'), countif(not skipped)) as pct_last_prediction,
        safe_divide(countif(within_30s), countif(not skipped)) as pct_within_30s,
        approx_quantiles(arrival_window_sec, 100)[offset(50)] as median_window_sec
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
    agg.* except (
        data_version, n_skipped, pct_shape_crossing, pct_last_prediction, pct_within_30s,
        median_window_sec
    ),
    r.route_name,
    r.route_long_name,
    agg.data_version,
    agg.n_skipped,
    coalesce(c.n_canceled_trips, 0) as n_canceled_trips,
    s.n_scheduled,
    -- Every visit that isn't skipped has an arrival, so a known delay marks an observed,
    -- scheduled stop event.
    safe_divide(agg.n_reported_events, s.n_scheduled) as pct_observed,
    agg.pct_shape_crossing,
    agg.pct_last_prediction,
    agg.pct_within_30s,
    agg.median_window_sec
from agg
left join canceled as c
    on c.route_id = agg.route_id
    and c.service_date_mst = agg.service_date_mst
left join scheduled as s
    on s.route_id = agg.route_id
    and s.service_date_mst = agg.service_date_mst
left join {{ ref('dim_route') }} as r
    on r.route_id = agg.route_id
    and r.is_latest_version
