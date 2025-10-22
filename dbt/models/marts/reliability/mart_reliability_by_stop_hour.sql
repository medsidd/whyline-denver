{{ config(
    materialized='incremental',
    partition_by={"field": "service_date_mst", "data_type": "date"},
    cluster_by=["stop_id"],
    meta={"allow_in_app": true}
) }}

with base as (
    select
        stop_id,
        route_id,
        service_date_mst,
        event_hour_mst,
        delay_sec
    from {{ ref('int_rt_events_resolved') }}
    where stop_id is not null
    {% if is_incremental() %}
        and service_date_mst >= (
            select ifnull(
                max(service_date_mst),
                date_sub(current_date("America/Denver"), interval 35 day)
            )
            from {{ this }}
        )
    {% endif %}
),
head AS (
    select
        stop_id,
        service_date_mst,
        extract(hour from event_ts_utc at time zone "America/Denver") as event_hour_mst,
        avg(headway_adherent) as headway_adherence_rate,
        approx_quantiles(obs_headway_sec, 100)[offset(50)] as obs_headway_sec_p50,
        approx_quantiles(obs_headway_sec, 100)[offset(90)] as obs_headway_sec_p90
    from {{ ref('int_headway_adherence') }}
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
        avg(case when abs(delay_sec) <= {{ var('on_time_sec', 300) }} then 1 else 0 end) as pct_on_time,
        avg(delay_sec) as mean_delay_sec,
        approx_quantiles(delay_sec, 100)[offset(90)] as p90_delay_sec
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
    current_timestamp() as build_run_at
from agg as a
left join head as h
    using (stop_id, service_date_mst, event_hour_mst)
left join route_mode as rm
    using (stop_id, service_date_mst, event_hour_mst)
