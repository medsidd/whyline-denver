{% macro gtfs_date_spine(start_date, end_date) %}
{#
Generate a date spine for GTFS schedule expansion.
Creates all dates between start_date and end_date with day-of-week info.
#}
with date_array as (
    select
        generate_date_array(
            {{ start_date }},
            {{ end_date }},
            interval 1 day
        ) as dates
),
unnested as (
    select date_value
    from date_array
    cross join unnest(dates) as date_value
)
select
    date_value as service_date,
    case extract(dayofweek from date_value)
        when 1 then 'sunday'
        when 2 then 'monday'
        when 3 then 'tuesday'
        when 4 then 'wednesday'
        when 5 then 'thursday'
        when 6 then 'friday'
        when 7 then 'saturday'
    end as day_of_week,
    extract(dayofweek from date_value) = 1 as is_sunday,
    extract(dayofweek from date_value) = 2 as is_monday,
    extract(dayofweek from date_value) = 3 as is_tuesday,
    extract(dayofweek from date_value) = 4 as is_wednesday,
    extract(dayofweek from date_value) = 5 as is_thursday,
    extract(dayofweek from date_value) = 6 as is_friday,
    extract(dayofweek from date_value) = 7 as is_saturday
from unnested
{% endmacro %}
