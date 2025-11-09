{{
    config(
        materialized='incremental',
        unique_key=['route_id', 'direction_id', 'stop_id', 'service_date_mst', 'event_ts_utc'],
        on_schema_change='fail',
        partition_by={
            'field': 'service_date_mst',
            'data_type': 'date',
            'granularity': 'day'
        },
        cluster_by=['route_id', 'stop_id']
    )
}}

{#
Cost optimization: Materialize to avoid repeated complex joins on GTFS schedule data
- Full refresh: 45-day lookback
- Incremental: Only process last 3 days to minimize overhead
- Uses MERGE strategy (not insert_overwrite) to avoid processing entire partition
#}
{% set lookback_days = var('schedule_lookback_days', 45) %}
{% set incremental_days = 3 %}

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
    {% if is_incremental() %}
        and service_date_mst >= date_sub(current_date("America/Denver"), interval {{ incremental_days }} day)
    {% else %}
        and service_date_mst >= date_sub(current_date("America/Denver"), interval {{ lookback_days }} day)
    {% endif %}
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
    {# No date filter on schedule data - it's static #}
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
