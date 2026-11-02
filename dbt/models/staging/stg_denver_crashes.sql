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
        ped_involved,
        _extract_date,
        _ingested_at
    from {{ source('raw', 'raw_crashes') }}
    where lon is not null
      and lat is not null
      -- Only the latest extract: Denver's five-year window as of that day. Older extracts would
      -- keep crashes that have aged out of the window. raw_crashes is partitioned by event date,
      -- so this subquery reads only recent partitions; the main scan still covers every extract.
      and _extract_date = (
          select max(_extract_date)
          from {{ source('raw', 'raw_crashes') }}
          where event_ts_utc >= timestamp_sub(current_timestamp(), interval 60 day)
      )
),
deduped as (
    select
        *,
        row_number() over (
            partition by crash_id
            -- A crash listed twice in one extract: the latest load wins, fully ordered so reruns agree
            order by _extract_date desc, _ingested_at desc, event_ts_utc desc, severity desc, lon, lat
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
