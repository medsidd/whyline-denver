{{
    config(
        enabled=false,
        materialized='incremental',
        unique_key=['feed_ts_utc', 'trip_id'],
        partition_by={'field': 'event_date_mst', 'data_type': 'date'},
        cluster_by=['route_id', 'trip_id'],
        incremental_strategy='merge',
        incremental_predicates=["DBT_INTERNAL_DEST.event_date_mst >= date_sub(current_date('America/Denver'), interval 3 day)"]
    )
}}

{#
LEGACY, frozen at the stop-visit cutover (enabled=false keeps the table but stops all runs and
tests). It sampled one predicted terminal arrival per poll and trip, not observed stop arrivals;
fct_stop_visit replaces it. Remove the flag only to rebuild history deliberately.
Silver: trip updates merged with vehicle positions, one row per feed poll x trip. Reported
delays only; schedule-derived delays and dimension keys are added in core.fct_trip_observation.
- Full refresh: 45-day lookback (raise rt_events_lookback_days to rebuild from all bronze)
- Incremental: last 12 hours of feeds
#}
{% set lookback_days = var('rt_events_lookback_days', 45) %}
{% set incremental_hours = var('rt_events_incremental_hours', 12) %}

with tu as (
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
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {% if is_incremental() %}{{ incremental_hours }} hour{% else %}{{ lookback_days }} day{% endif %})
      and date(feed_ts_utc) >= date_sub(current_date(), interval {% if is_incremental() %}1{% else %}{{ lookback_days }}{% endif %} day)  -- Explicit partition filter
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
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval {% if is_incremental() %}{{ incremental_hours }} hour{% else %}{{ lookback_days }} day{% endif %})
      and date(feed_ts_utc) >= date_sub(current_date(), interval {% if is_incremental() %}1{% else %}{{ lookback_days }}{% endif %} day)  -- Explicit partition filter
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
    -- A NULL trip_id never matches the MERGE key, so these rows were re-inserted every run
    where coalesce(tu.trip_id, vp.trip_id) is not null
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
    r.arrival_delay_sec_raw as arrival_delay_sec,
    r.departure_delay_sec_raw as departure_delay_sec,
    r.schedule_relationship,
    r.vehicle_id,
    r.vehicle_label,
    r.lon,
    r.lat,
    r.bearing,
    r.speed_mps,
    r.geom,
    r.event_ts_utc,
    {{ date_mst('r.event_ts_utc') }} as event_date_mst,
    {{ hour_mst('r.event_ts_utc') }} as event_hour_mst
from ranked as r
where r.trip_rank = 1
