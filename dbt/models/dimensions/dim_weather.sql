{% if var('weather_station', none) is none %}
    {{ exceptions.raise_compiler_error(
        "dim_weather requires 'weather_station' dbt variable. "
        ~ "Set it in dbt_project.yml vars or --vars '{weather_station: USW00023062}'"
    ) }}
{% endif %}

{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "dim"}
) }}

select
    date           as service_date_mst,
    snow_day,
    precip_bin,
    tmin_c,
    tmax_c,
    tavg_c,
    snow_mm,
    precip_mm
from {{ ref('stg_weather') }}
where station = '{{ var("weather_station") }}'
