{# Conformed calendar; role-plays as service, event, crash, and weather date #}
select
    date_day,
    extract(year from date_day) as year,
    extract(quarter from date_day) as quarter,
    extract(month from date_day) as month,
    format_date('%B', date_day) as month_name,
    extract(day from date_day) as day_of_month,
    mod(extract(dayofweek from date_day) + 5, 7) + 1 as iso_day_of_week,
    format_date('%A', date_day) as day_name,
    extract(dayofweek from date_day) in (1, 7) as is_weekend,
    date_trunc(date_day, isoweek) as iso_week_start
from unnest(
    generate_date_array(date '2025-01-01', date_add(current_date('America/Denver'), interval 60 day))
) as date_day
