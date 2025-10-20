{{ config(materialized='view') }}

with base as (
    select
        crash_id,
        event_ts_utc,
        severity,
        severity_text,
        lon,
        lat,
        roadway_name,
        on_route,
        off_route,
        bike_involved,
        ped_involved
    from {{ source('raw', 'raw_crashes') }}
    where lon is not null
      and lat is not null
),
deduped as (
    select
        *,
        row_number() over (
            partition by crash_id
            order by event_ts_utc desc, severity desc
        ) as crash_rank
    from base
)
select
    crash_id,
    event_ts_utc,
    severity,
    severity_text,
    {{ make_point('lon', 'lat') }} as geom,
    roadway_name,
    on_route,
    off_route,
    bike_involved,
    ped_involved,
    {{ date_mst('event_ts_utc') }} as event_date_mst,
    {{ hour_mst('event_ts_utc') }} as event_hour_mst
from deduped
where crash_rank = 1
