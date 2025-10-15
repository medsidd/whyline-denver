{{ config(materialized='view') }}

with tu as (
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
)
select
    feed_ts_utc,
    trip_id,
    route_id,
    tu_entity_id,
    vp_entity_id,
    stop_id,
    stop_sequence,
    arrival_delay_sec,
    departure_delay_sec,
    schedule_relationship,
    vehicle_id,
    vehicle_label,
    lon,
    lat,
    bearing,
    speed_mps,
    geom,
    event_ts_utc,
    {{ date_mst('event_ts_utc') }} as event_date_mst,
    {{ hour_mst('event_ts_utc') }} as event_hour_mst
from j
