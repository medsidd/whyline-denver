{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": true}
) }}

{#
How crowded each route's trips were, by direction, service date and the hour the trip left its
first stop. A trip's level is the highest occupancy reported anywhere on it; shares count only
trips with occupancy data, and pct_trips_with_data says how many that is. Published after the
coverage check; until then allow_in_app is false.
#}
{% set days = var('crowding_days', 3) %}

with stops as (
    select *
    from {{ ref('fct_trip_occupancy') }}
    where route_id is not null
    {% if is_incremental() %}
        and service_date >= date_sub(current_date('America/Denver'), interval {{ days }} day)
    {% endif %}
),
peaks as (
    -- Where each trip's highest level was first reported.
    select service_date, trip_id, stop_id as peak_stop_id
    from stops
    where max_level is not null
    qualify row_number() over (
        partition by service_date, trip_id order by max_level desc, stop_sequence
    ) = 1
),
trips as (
    select
        s.service_date,
        s.trip_id,
        any_value(s.route_id) as route_id,
        any_value(s.direction_id) as direction_id,
        {{ hour_mst('min(s.event_ts_utc)') }} as departure_hour_mst,
        max(s.max_level) as trip_level,
        any_value(p.peak_stop_id) as peak_stop_id
    from stops as s
    left join peaks as p
        on p.service_date = s.service_date
        and p.trip_id = s.trip_id
    group by 1, 2
),
peak_mode as (
    -- The stop where crowded trips (few seats or worse) most often peaked.
    select route_id, direction_id, service_date, departure_hour_mst, peak_stop_id
    from trips
    where trip_level >= 2
    group by 1, 2, 3, 4, 5
    qualify row_number() over (
        partition by route_id, direction_id, service_date, departure_hour_mst
        order by count(*) desc, peak_stop_id
    ) = 1
)

select
    t.route_id,
    t.direction_id,
    t.service_date as service_date_mst,
    t.departure_hour_mst,
    count(*) as n_trips,
    countif(t.trip_level is not null) as n_trips_with_data,
    countif(t.trip_level is not null) / count(*) as pct_trips_with_data,
    avg(if(t.trip_level is null, null, if(t.trip_level >= 2, 1, 0))) as pct_trips_few_seats_or_worse,
    avg(if(t.trip_level is null, null, if(t.trip_level >= 3, 1, 0))) as pct_trips_standing_or_worse,
    any_value(m.peak_stop_id) as peak_stop_id_mode,
    current_timestamp() as build_run_at
from trips as t
left join peak_mode as m
    on m.route_id = t.route_id
    and m.direction_id = t.direction_id
    and m.service_date = t.service_date
    and m.departure_hour_mst = t.departure_hour_mst
group by 1, 2, 3, 4
