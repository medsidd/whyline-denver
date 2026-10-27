{# Grain: one station x date (periodic snapshot); marts select var('weather_station') #}
select
    date as weather_date,
    station,
    precip_mm,
    snow_mm,
    tmin_c,
    tmax_c,
    tavg_c,
    snow_day > 0 as snow_day,
    precip_bin
from {{ ref('stg_weather') }}
