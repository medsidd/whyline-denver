{{
    config(
        enabled=false,
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['feed_ts_utc', 'trip_id'],
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['route_id', 'stop_id'],
        incremental_predicates=["DBT_INTERNAL_DEST.service_date_mst >= date_sub(current_date('America/Denver'), interval 3 day)"]
    )
}}

{#
LEGACY, frozen at the stop-visit cutover (enabled=false keeps the table but stops all runs and
tests). It sampled one predicted terminal arrival per poll and trip, not observed stop arrivals;
fct_stop_visit replaces it. Remove the flag only to rebuild history deliberately.
Grain: one realtime observation per feed poll x trip (sampled, not every arrival).
Delay resolution: the reported delay, else event time minus the scheduled time for the
same trip/stop/date, else NULL in *_raw and 0 in delay_sec (counted as on time).
Natural keys are carried next to the surrogate keys so the 15-minute marts avoid dim joins.
#}

with obs as (
    select
        feed_ts_utc,
        trip_id,
        route_id,
        stop_id,
        stop_sequence,
        event_ts_utc,
        event_date_mst,
        event_hour_mst,
        arrival_delay_sec,
        departure_delay_sec,
        schedule_relationship,
        vehicle_id,
        vehicle_label,
        lat,
        lon,
        bearing,
        speed_mps
    from {{ ref('stg_rt_events') }}
    {% if is_incremental() %}
    where event_date_mst >= date_sub(current_date('America/Denver'), interval 3 day)
      and feed_ts_utc >= timestamp_sub(current_timestamp(), interval {{ var('rt_events_incremental_hours', 12) }} hour)
    {% endif %}
),
sched as (
    select
        trip_id,
        stop_id,
        stop_sequence,
        service_date_mst,
        sched_arrival_ts_mst,
        sched_departure_ts_mst
    from {{ ref('fct_scheduled_stop_time') }}
    {% if is_incremental() %}
    -- Constant bounds so BigQuery prunes; the schedule extends ~30 days ahead
    where service_date_mst between date_sub(current_date('America/Denver'), interval 3 day)
        and date_add(current_date('America/Denver'), interval 1 day)
    {% endif %}
),
resolved as (
    select
        o.*,
        coalesce(
            o.arrival_delay_sec,
            timestamp_diff(o.event_ts_utc, s.sched_arrival_ts_mst, second)
        ) as arrival_delay_resolved_sec,
        coalesce(
            o.departure_delay_sec,
            timestamp_diff(o.event_ts_utc, s.sched_departure_ts_mst, second)
        ) as departure_delay_resolved_sec
    from obs as o
    left join sched as s
        on o.trip_id = s.trip_id
        and o.stop_id = s.stop_id
        and o.stop_sequence = s.stop_sequence
        and o.event_date_mst = s.service_date_mst
)

select
    r.feed_ts_utc,
    r.trip_id,
    r.route_id,
    r.stop_id,
    r.stop_sequence,
    r.event_date_mst as service_date_mst,
    r.event_hour_mst,
    r.event_ts_utc,
    coalesce(dt.trip_key, -1) as trip_key,
    coalesce(dr.route_key, -1) as route_key,
    coalesce(ds.stop_key, -1) as stop_key,
    dt.direction_id,
    r.arrival_delay_sec as arrival_delay_reported_sec,
    r.departure_delay_sec as departure_delay_reported_sec,
    r.arrival_delay_sec is not null or r.departure_delay_sec is not null as is_delay_reported,
    coalesce(r.arrival_delay_resolved_sec, r.departure_delay_resolved_sec) as delay_sec_raw,
    coalesce(r.arrival_delay_resolved_sec, r.departure_delay_resolved_sec, 0) as delay_sec,
    r.schedule_relationship,
    r.vehicle_id,
    r.vehicle_label,
    r.lat,
    r.lon,
    r.bearing,
    r.speed_mps
from resolved as r
left join {{ ref('dim_trip') }} as dt
    on dt.trip_id = r.trip_id
    and r.event_date_mst between dt.valid_from and dt.valid_to
left join {{ ref('dim_route') }} as dr
    on dr.route_id = r.route_id
    and r.event_date_mst between dr.valid_from and dr.valid_to
left join {{ ref('dim_stop') }} as ds
    on ds.stop_id = r.stop_id
    and r.event_date_mst between ds.valid_from and ds.valid_to
