{{ config(materialized='view') }}

{#
Silver: hourly weather, one row per station and UTC hour from the latest extract that has it.
Extracts overlap by 10 days, so a later extract replaces forecast-model hours with archive ones.
#}
select
    ts_utc,
    station,
    precip_mm,
    snowfall_mm,
    temp_c,
    wind_kmh,
    source
from {{ source('raw', 'raw_weather_hourly') }}
where ts_utc is not null
qualify row_number() over (partition by station, ts_utc order by _extract_date desc, _ingested_at desc) = 1
