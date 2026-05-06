{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "dim"}
) }}

{% set start_date = var('dim_date_start', '2022-01-01') %}
{% set offset_days = var('dim_date_end_offset_days', 365) %}

with date_spine as (
    select date_value
    from unnest(
        generate_date_array(
            date '{{ start_date }}',
            date_add(current_date('America/Denver'), interval {{ offset_days }} day),
            interval 1 day
        )
    ) as date_value
)

select
    date_value                                          as service_date_mst,
    extract(dayofweek from date_value)                  as day_of_week,
    case extract(dayofweek from date_value)
        when 1 then 'Sunday'
        when 2 then 'Monday'
        when 3 then 'Tuesday'
        when 4 then 'Wednesday'
        when 5 then 'Thursday'
        when 6 then 'Friday'
        when 7 then 'Saturday'
    end                                                 as day_name,
    extract(dayofweek from date_value) in (1, 7)        as is_weekend,
    extract(month from date_value)                      as month_num,
    format_date('%B', date_value)                       as month_name,
    extract(quarter from date_value)                    as quarter,
    extract(year from date_value)                       as year,
    case
        when extract(month from date_value) in (12, 1, 2) then 'winter'
        when extract(month from date_value) in (3, 4, 5)  then 'spring'
        when extract(month from date_value) in (6, 7, 8)  then 'summer'
        else 'fall'
    end                                                 as season
from date_spine
