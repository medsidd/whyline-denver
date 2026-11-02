{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": false}
) }}

{#
How long trips really take, end to end, per route, direction, pattern (first and last stop)
and service date: from leaving the first stop to reaching the last, both timed to within 30 s.
buffer_time_index = (p90 - p50) / p50 is the extra share of time to allow to be on time 9 times
in 10; it includes the difference between peak and off-peak trips. Published after the
stop-visit review.
#}
{% set days = var('segment_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('segment_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with trips as (
    select
        service_date,
        trip_id,
        any_value(route_id) as route_id,
        any_value(direction_id) as direction_id,
        max(if(stop_role = 'first', stop_id, null)) as first_stop_id,
        max(if(stop_role = 'last', stop_id, null)) as last_stop_id,
        max(if(stop_role = 'first' and arrival_method = 'origin_departure' and within_30s, arrival_ts_utc, null))
            as start_ts,
        max(if(stop_role = 'last' and within_30s, arrival_ts_utc, null)) as end_ts,
        max(if(stop_role = 'first', coalesce(scheduled_departure_ts, scheduled_arrival_ts), null))
            as scheduled_start_ts,
        max(if(stop_role = 'last', coalesce(scheduled_arrival_ts, scheduled_departure_ts), null))
            as scheduled_end_ts
    from {{ ref('fct_stop_visit') }}
    where service_date between {{ first }} and {{ last }}
    group by 1, 2
),
runtimes as (
    select
        *,
        timestamp_diff(end_ts, start_ts, second) as runtime_sec,
        timestamp_diff(scheduled_end_ts, scheduled_start_ts, second) as scheduled_runtime_sec
    from trips
    where route_id is not null and end_ts > start_ts
),
grouped as (
    select
        route_id,
        direction_id,
        first_stop_id,
        last_stop_id,
        service_date,
        count(*) as n_trips,
        approx_quantiles(runtime_sec, 100)[offset(50)] as p50_runtime_sec,
        approx_quantiles(runtime_sec, 100)[offset(90)] as p90_runtime_sec,
        approx_quantiles(scheduled_runtime_sec, 100)[offset(50)] as scheduled_runtime_sec
    from runtimes
    group by 1, 2, 3, 4, 5
)

select
    g.route_id,
    g.direction_id,
    g.first_stop_id,
    a.stop_name as first_stop_name,
    g.last_stop_id,
    b.stop_name as last_stop_name,
    g.service_date as service_date_mst,
    g.n_trips,
    round(g.p50_runtime_sec / 60, 1) as p50_runtime_min,
    round(g.p90_runtime_sec / 60, 1) as p90_runtime_min,
    round(g.scheduled_runtime_sec / 60, 1) as scheduled_runtime_min,
    round(safe_divide(g.p90_runtime_sec - g.p50_runtime_sec, g.p50_runtime_sec), 3) as buffer_time_index,
    current_timestamp() as build_run_at
from grouped as g
left join {{ ref('dim_stop') }} as a
    on a.stop_id = g.first_stop_id
    and a.is_current
left join {{ ref('dim_stop') }} as b
    on b.stop_id = g.last_stop_id
    and b.is_current
