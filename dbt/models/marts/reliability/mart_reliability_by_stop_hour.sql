{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    unique_key=['stop_id', 'service_date_mst', 'event_hour_mst'],
    partition_by={"field": "service_date_mst", "data_type": "date"},
    cluster_by=["stop_id"],
    on_schema_change='append_new_columns',
    full_refresh=false,
    meta={"allow_in_app": true}
) }}

{#
Observed stop visits per stop, service date and arrival hour (Denver). On time and unknown
delays as in mart_reliability_by_route_day. Observed headway: time since the previous visit at
the same stop by the same route and direction; it is adherent when within headway_tol_ratio of
that visit's scheduled headway (the gap to the previous scheduled trip), so a missed trip shows
as a long observed headway. Backfilled visits stay out until published (publish_backfill).
Each run replaces whole service-date partitions, so a rebuilt date keeps no legacy rows. Full
refreshes are disabled because pre-cutover partitions can no longer be rebuilt (their legacy
models are disabled); rebuild a longer span with a wider stop_hour_window_days.
#}
{% set window_days = var('stop_hour_window_days', 1) %}
{% set versions = "'stream_v1', 'backfill_v1'" if var('publish_backfill', false) else "'stream_v1'" %}

with base as (
    select
        stop_id,
        route_id,
        direction_id,
        service_date as service_date_mst,
        arrival_hour_mst as event_hour_mst,
        arrival_ts_utc,
        delay_sec,
        scheduled_headway_sec,
        arrival_method,
        within_30s,
        data_version
    from {{ ref('fct_stop_visit') }}
    where stop_id is not null
      and arrival_ts_utc is not null
      and data_version in ({{ versions }})
    {% if is_incremental() %}
        and service_date >= date_sub(current_date("America/Denver"), interval {{ window_days }} day)
    {% endif %}
),
headways as (
    select
        *,
        timestamp_diff(
            arrival_ts_utc,
            lag(arrival_ts_utc) over (
                partition by stop_id, route_id, direction_id, service_date_mst
                order by arrival_ts_utc
            ),
            second
        ) as obs_headway_sec
    from base
),
head as (
    select
        stop_id,
        service_date_mst,
        event_hour_mst,
        avg(
            case
                when obs_headway_sec is null
                    or scheduled_headway_sec is null
                    or scheduled_headway_sec <= 0 then null
                when abs(obs_headway_sec - scheduled_headway_sec) / scheduled_headway_sec
                    <= {{ var('headway_tol_ratio', 0.5) }} then 1
                else 0
            end
        ) as headway_adherence_rate,
        approx_quantiles(obs_headway_sec, 100)[offset(50)] as obs_headway_sec_p50,
        approx_quantiles(obs_headway_sec, 100)[offset(90)] as obs_headway_sec_p90
    from headways
    group by
        stop_id,
        service_date_mst,
        event_hour_mst
),
agg as (
    select
        stop_id,
        service_date_mst,
        event_hour_mst,
        count(*) as n_events,
        avg(
            case
                when delay_sec is null then null
                when delay_sec > -{{ var('on_time_early_sec', 60) }}
                    and delay_sec <= {{ var('on_time_late_sec', 300) }} then 1
                else 0
            end
        ) as pct_on_time,
        avg(delay_sec) as mean_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(90)] as p90_delay_sec,
        if(count(distinct data_version) > 1, 'mixed', any_value(data_version)) as data_version,
        countif(delay_sec is not null) as n_reported_events,
        safe_divide(countif(within_30s), count(*)) as pct_within_30s,
        safe_divide(
            countif(arrival_method like '%crossing%' or arrival_method = 'origin_departure'),
            count(*)
        ) as pct_shape_crossing
    from base
    group by
        stop_id,
        service_date_mst,
        event_hour_mst
),
route_mode as (
    select
        stop_id,
        service_date_mst,
        event_hour_mst,
        array_agg(route_id order by route_events desc, route_id limit 1)[offset(0)] as route_id_mode
    from (
        select
            stop_id,
            service_date_mst,
            event_hour_mst,
            route_id,
            count(*) as route_events
        from base
        where route_id is not null
        group by
            stop_id,
            service_date_mst,
            event_hour_mst,
            route_id
    )
    group by
        stop_id,
        service_date_mst,
        event_hour_mst
)

select
    a.stop_id,
    a.service_date_mst,
    a.event_hour_mst,
    a.n_events,
    a.pct_on_time,
    a.mean_delay_sec,
    a.p90_delay_sec,
    coalesce(rm.route_id_mode, 'unknown') as route_id_mode,
    h.headway_adherence_rate,
    h.obs_headway_sec_p50,
    h.obs_headway_sec_p90,
    current_timestamp() as build_run_at,
    s.stop_name,
    s.lat,
    s.lon,
    r.route_name as route_name_mode,
    a.data_version,
    a.n_reported_events,
    a.pct_within_30s,
    a.pct_shape_crossing
from agg as a
left join head as h
    using (stop_id, service_date_mst, event_hour_mst)
left join route_mode as rm
    using (stop_id, service_date_mst, event_hour_mst)
left join {{ ref('dim_stop') }} as s
    on s.stop_id = a.stop_id
    and s.is_latest_version
left join {{ ref('dim_route') }} as r
    on r.route_id = rm.route_id_mode
    and r.is_latest_version
