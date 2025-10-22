{{ config(materialized='view') }}

with trips as (
    select
        trip_id,
        direction_id,
        trip_headsign
    from {{ ref('stg_gtfs_trips') }}
),
tu as (
    select
        feed_ts_utc,
        entity_id as tu_entity_id,
        trip_id,
        route_id,
        stop_id,
        stop_sequence,
        arrival_delay_sec,
        departure_delay_sec,
        schedule_relationship,
        event_ts_utc as tu_event_ts_utc
    from {{ source('raw','raw_gtfsrt_trip_updates') }}
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
        tu.arrival_delay_sec,
        tu.departure_delay_sec,
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
    r.arrival_delay_sec,
    r.departure_delay_sec,
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
where r.trip_rank = 1
