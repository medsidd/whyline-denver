{{ config(materialized='view') }}

with obs as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        event_ts_utc,
        obs_headway_sec
    from {{ ref('int_stop_headways_observed') }}
    where obs_headway_sec is not null
),
sch as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        sched_arrival_ts_mst,
        sch_headway_sec
    from {{ ref('int_stop_headways_scheduled') }}
    where sch_headway_sec is not null
),
nearest as (
    select
        o.route_id,
        o.direction_id,
        o.stop_id,
        o.service_date_mst,
        o.event_ts_utc,
        o.obs_headway_sec,
        s.sch_headway_sec,
        abs(timestamp_diff(o.event_ts_utc, s.sched_arrival_ts_mst, second)) as dt_abs
    from obs as o
    join sch as s
        on o.route_id = s.route_id
        and coalesce(o.direction_id, -1) = coalesce(s.direction_id, -1)
        and o.stop_id = s.stop_id
        and o.service_date_mst = s.service_date_mst
    qualify row_number() over (
        partition by o.route_id, o.direction_id, o.stop_id, o.service_date_mst, o.event_ts_utc
        order by dt_abs
    ) = 1
)

select
    route_id,
    direction_id,
    stop_id,
    service_date_mst,
    event_ts_utc,
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
