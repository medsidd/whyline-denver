{{ config(materialized='view') }}

with base as (
    select
        date,
        station,
        snow_day,
        precip_bin,
        precip_mm
    from {{ ref('stg_weather') }}
    {% if var('weather_station') is not none %}
        where station = '{{ var("weather_station") }}'
    {% endif %}
),
aggregated as (
    select
        date as service_date_mst,
        max(coalesce(snow_day, 0)) as snow_day_flag,
        array_agg(
            precip_bin
            ignore nulls
            order by precip_mm desc
        )[offset(0)] as precip_bin
    from base
    group by service_date_mst
)

select
    service_date_mst,
    snow_day_flag > 0 as snow_day,
    precip_bin
from aggregated
