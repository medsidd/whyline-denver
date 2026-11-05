{{
    config(
        enabled=false,
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='stop_arrival_key',
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['route_id', 'stop_id'],
        incremental_predicates=["DBT_INTERNAL_DEST.service_date_mst >= date_sub(current_date('America/Denver'), interval 4 day)"]
    )
}}

{#
LEGACY, frozen at the stop-visit cutover (enabled=false keeps the table but stops all runs and
tests). It sampled one predicted terminal arrival per poll and trip, not observed stop arrivals;
fct_stop_visit replaces it. Remove the flag only to rebuild history deliberately.
Grain: one observed stop event per route x direction x stop x service date x event time,
with the observed headway, the nearest scheduled headway, and an adherence flag.
Incremental: 3 days; full refresh: rt_events_lookback_days.
#}
{% set window_days = 3 if is_incremental() else var('rt_events_lookback_days', 45) %}

with obs_events as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        event_ts_utc,
        any_value(route_key) as route_key,
        any_value(stop_key) as stop_key
    from {{ ref('fct_trip_observation') }}
    where event_ts_utc is not null
      and service_date_mst >= date_sub(current_date('America/Denver'), interval {{ window_days }} day)
    group by route_id, direction_id, stop_id, service_date_mst, event_ts_utc
),
obs as (
    select
        *,
        timestamp_diff(
            event_ts_utc,
            lag(event_ts_utc) over (
                partition by route_id, direction_id, stop_id, service_date_mst
                order by event_ts_utc
            ),
            second
        ) as obs_headway_sec
    from obs_events
),
sched_events as (
    select distinct
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        sched_arrival_ts_mst
    from {{ ref('fct_scheduled_stop_time') }}
    where sched_arrival_ts_mst is not null
      -- Constant bounds so BigQuery prunes; the schedule extends ~30 days ahead
      and service_date_mst between date_sub(current_date('America/Denver'), interval {{ window_days }} day)
        and date_add(current_date('America/Denver'), interval 1 day)
),
sch as (
    select
        *,
        timestamp_diff(
            sched_arrival_ts_mst,
            lag(sched_arrival_ts_mst) over (
                partition by route_id, direction_id, stop_id, service_date_mst
                order by sched_arrival_ts_mst
            ),
            second
        ) as sch_headway_sec
    from sched_events
),
nearest as (
    select
        o.route_id,
        o.direction_id,
        o.stop_id,
        o.service_date_mst,
        o.event_ts_utc,
        o.route_key,
        o.stop_key,
        o.obs_headway_sec,
        s.sch_headway_sec,
        abs(timestamp_diff(o.event_ts_utc, s.sched_arrival_ts_mst, second)) as dt_abs
    from obs as o
    join sch as s
        on o.route_id = s.route_id
        and coalesce(o.direction_id, -1) = coalesce(s.direction_id, -1)
        and o.stop_id = s.stop_id
        and o.service_date_mst = s.service_date_mst
    where o.obs_headway_sec is not null
      and s.sch_headway_sec is not null
    qualify row_number() over (
        partition by o.route_id, o.direction_id, o.stop_id, o.service_date_mst, o.event_ts_utc
        order by dt_abs
    ) = 1
)

select
    farm_fingerprint(concat(
        route_id, '|', coalesce(cast(direction_id as string), ''), '|', stop_id, '|',
        cast(service_date_mst as string), '|', cast(event_ts_utc as string)
    )) as stop_arrival_key,
    route_id,
    direction_id,
    stop_id,
    service_date_mst,
    event_ts_utc,
    route_key,
    stop_key,
    obs_headway_sec,
    sch_headway_sec,
    dt_abs,
    case
        when dt_abs <= {{ var('sched_match_tol_sec', 1800) }}
         and sch_headway_sec > 0
         and abs(obs_headway_sec - sch_headway_sec) / sch_headway_sec <= {{ var('headway_tol_ratio', 0.5) }}
        then 1
        else 0
    end as headway_adherent
from nearest
