{#
The next Wednesday, Saturday and Sunday in the published schedule, one sample date per day type.
Holiday service shows if a holiday falls on a sample date.
#}
{% macro schedule_sample_dates() %}
    select
        case format_date('%a', service_date_mst)
            when 'Wed' then 'weekday'
            when 'Sat' then 'saturday'
            else 'sunday'
        end as day_type,
        min(service_date_mst) as sample_date
    from {{ ref('fct_scheduled_stop_time') }}
    where
        service_date_mst between current_date('America/Denver')
        and date_add(current_date('America/Denver'), interval 13 day)
        and format_date('%a', service_date_mst) in ('Wed', 'Sat', 'Sun')
    group by 1
{% endmacro %}
