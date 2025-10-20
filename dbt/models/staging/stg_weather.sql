{{ config(materialized='view') }}

with base as (
    select
        date,
        station,
        snow_mm,
        precip_mm,
        tmin_c,
        tmax_c,
        tavg_c,
        snow_day,
        precip_bin,
        _ingested_at
    from {{ source('raw','raw_weather_daily') }}
),
deduped as (
    select
        *,
        row_number() over (
            partition by date, station
            order by _ingested_at desc
        ) as record_rank
    from base
)

select
    date,
    station,
    snow_mm,
    precip_mm,
    tmin_c,
    tmax_c,
    tavg_c,
    snow_day,
    precip_bin
from deduped
where record_rank = 1
