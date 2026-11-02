{# Grain: one station x UTC hour (Open-Meteo at the station's coordinates); marts select var('weather_station'). #}
select
    ts_utc,
    station,
    {{ date_mst('ts_utc') }} as date_mst,
    {{ hour_mst('ts_utc') }} as hour_mst,
    precip_mm,
    snowfall_mm,
    temp_c,
    wind_kmh,
    source
from {{ ref('stg_weather_hourly') }}
