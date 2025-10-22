{{ config(materialized='view') }}

with base as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        sched_arrival_ts_mst
    from {{ ref('int_scheduled_arrivals') }}
    where sched_arrival_ts_mst is not null
),
deduped as (
    select
        route_id,
        direction_id,
        stop_id,
        service_date_mst,
        sched_arrival_ts_mst,
        row_number() over (
            partition by route_id, direction_id, stop_id, service_date_mst, sched_arrival_ts_mst
            order by sched_arrival_ts_mst
        ) as arrival_rank
    from base
)

select
    route_id,
    direction_id,
    stop_id,
    service_date_mst,
    sched_arrival_ts_mst,
    timestamp_diff(
        sched_arrival_ts_mst,
        lag(sched_arrival_ts_mst) over (
            partition by route_id, direction_id, stop_id, service_date_mst
            order by sched_arrival_ts_mst
        ),
        second
    ) as sch_headway_sec
from deduped
where arrival_rank = 1
