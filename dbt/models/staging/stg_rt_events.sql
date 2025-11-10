{{
    config(
        materialized='incremental',
        unique_key=['feed_ts_utc', 'trip_id'],
        partition_by={'field': 'event_date_mst', 'data_type': 'date'},
        cluster_by=['route_id', 'trip_id'],
        incremental_strategy='merge'
    )
}}

{#
Cost optimization: Materialize as incremental table to avoid repeated scans of raw GTFS-RT data.
- Full refresh: 45-day lookback
- Incremental: Only process last 3 days to minimize overhead
#}
{% set lookback_days = var('rt_events_lookback_days', 45) %}
{% set incremental_days = 3 %}

with trips as (
    select
        trip_id,
        direction_id,
        trip_headsign
    from {{ ref('stg_gtfs_trips') }}
),
scheduled as (
    select
        trip_id,
        stop_id,
        stop_sequence,
        sched_arrival_ts_mst,
        sched_departure_ts_mst,
        service_date_mst
    from {{ ref('int_scheduled_arrivals') }}
),
tu as (
    select
        feed_ts_utc,
        entity_id as tu_entity_id,
        trip_id,
        route_id,
        stop_id,
        stop_sequence,
        arrival_delay_sec as arrival_delay_sec_raw,
        departure_delay_sec as departure_delay_sec_raw,
        schedule_relationship,
        event_ts_utc as tu_event_ts_utc
    from {{ source('raw','raw_gtfsrt_trip_updates') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {% if is_incremental() %}{{ incremental_days }}{% else %}{{ lookback_days }}{% endif %} day)
),
vp as (
    select
        feed_ts_utc,
        entity_id as vp_entity_id,
        trip_id,
        route_id,
        vehicle_id,
        vehicle_label,
        lon,
        lat,
        bearing,
        speed_mps,
        event_ts_utc as vp_event_ts_utc
    from {{ source('raw','raw_gtfsrt_vehicle_positions') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {% if is_incremental() %}{{ incremental_days }}{% else %}{{ lookback_days }}{% endif %} day)
),
j as (
    select
        coalesce(tu.feed_ts_utc, vp.feed_ts_utc) as feed_ts_utc,
        coalesce(tu.trip_id, vp.trip_id) as trip_id,
        coalesce(tu.route_id, vp.route_id) as route_id,
        tu.tu_entity_id,
        vp.vp_entity_id,
        tu.stop_id,
        tu.stop_sequence,
        tu.arrival_delay_sec_raw,
        tu.departure_delay_sec_raw,
        tu.schedule_relationship,
        vp.vehicle_id,
        vp.vehicle_label,
        vp.lon,
        vp.lat,
        vp.bearing,
        vp.speed_mps,
        {{ make_point('vp.lon','vp.lat') }} as geom,
        coalesce(tu.tu_event_ts_utc, vp.vp_event_ts_utc, coalesce(tu.feed_ts_utc, vp.feed_ts_utc)) as event_ts_utc
    from tu
    full outer join vp
        on tu.feed_ts_utc = vp.feed_ts_utc
        and tu.trip_id = vp.trip_id
        and tu.route_id = vp.route_id
),
ranked as (
    select
        *,
        row_number() over (
            partition by feed_ts_utc, trip_id
            order by event_ts_utc desc, tu_entity_id desc, vp_entity_id desc
        ) as trip_rank
    from j
)
select
    r.feed_ts_utc,
    r.trip_id,
    r.route_id,
    r.tu_entity_id,
    r.vp_entity_id,
    r.stop_id,
    r.stop_sequence,
    -- Use raw delay values if available, otherwise calculate from schedule
    coalesce(
        r.arrival_delay_sec_raw,
        case
            when s.sched_arrival_ts_mst is not null and r.event_ts_utc is not null
            then timestamp_diff(r.event_ts_utc, s.sched_arrival_ts_mst, second)
        end
    ) as arrival_delay_sec,
    coalesce(
        r.departure_delay_sec_raw,
        case
            when s.sched_departure_ts_mst is not null and r.event_ts_utc is not null
            then timestamp_diff(r.event_ts_utc, s.sched_departure_ts_mst, second)
        end
    ) as departure_delay_sec,
    r.schedule_relationship,
    r.vehicle_id,
    r.vehicle_label,
    r.lon,
    r.lat,
    r.bearing,
    r.speed_mps,
    r.geom,
    r.event_ts_utc,
    t.direction_id,
    t.trip_headsign,
    {{ date_mst('r.event_ts_utc') }} as event_date_mst,
    {{ hour_mst('r.event_ts_utc') }} as event_hour_mst
from ranked as r
left join trips as t
    on r.trip_id = t.trip_id
left join scheduled as s
    on r.trip_id = s.trip_id
    and r.stop_id = s.stop_id
    and r.stop_sequence = s.stop_sequence
    and s.service_date_mst = {{ date_mst('r.event_ts_utc') }}
where r.trip_rank = 1
