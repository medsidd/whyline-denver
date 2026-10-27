{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['trip_id', 'stop_id']
    )
}}

{#
Grain: one scheduled stop per trip x stop_sequence x service date.
Each date is expanded from the GTFS files that were current on it (as-of join), so the
past keeps the schedule as published. The loader skips files whose content did not change,
so each file has its own extract history and is resolved separately. Nightly incremental
runs replace today through +lookahead from each file's latest extract, filtered by a
constant so BigQuery reads one partition; a full refresh rebuilds from schedule_history_start.
#}
{% set lookahead_days = var('schedule_lookahead_days', 30) %}
{% set files = {
    'calendar': 'raw_gtfs_calendar',
    'calendar_dates': 'raw_gtfs_calendar_dates',
    'trips': 'raw_gtfs_trips',
    'stop_times': 'raw_gtfs_stop_times',
} %}
{% set extract_filter = {} %}
{% for name, table in files.items() %}
    {% if is_incremental() %}
        {% do extract_filter.update({name: '_extract_date = ' ~ latest_extract_date(source('raw', table))}) %}
    {% else %}
        {% do extract_filter.update({name: 'true'}) %}
    {% endif %}
{% endfor %}
{% if is_incremental() %}
    {% set start_date = "current_date('America/Denver')" %}
{% else %}
    {% set start_date = "date '" ~ var('schedule_history_start', '2025-10-23') ~ "'" %}
{% endif %}

with calendar as (
    select * from {{ ref('stg_gtfs_calendar') }} where {{ extract_filter['calendar'] }}
),
calendar_dates as (
    select * from {{ ref('stg_gtfs_calendar_dates') }} where {{ extract_filter['calendar_dates'] }}
),
trips as (
    select _extract_date, trip_id, route_id, direction_id, service_id
    from {{ ref('stg_gtfs_trips') }}
    where {{ extract_filter['trips'] }}
),
stop_times as (
    select _extract_date, trip_id, stop_id, stop_sequence, arrival_time, departure_time
    from {{ ref('stg_gtfs_stop_times') }}
    where {{ extract_filter['stop_times'] }}
),
extracts as (
    {%- for name in files %}
    select distinct '{{ name }}' as gtfs_file, _extract_date from {{ name }}
    {%- if not loop.last %} union all{% endif %}
    {%- endfor %}
),
date_extract as (
    -- Per file: latest extract on or before each date; dates before its first extract use the first
    select
        service_date
        {%- for name in files %},
        coalesce(
            max(if(e.gtfs_file = '{{ name }}' and e._extract_date <= service_date, e._extract_date, null)),
            min(if(e.gtfs_file = '{{ name }}', e._extract_date, null))
        ) as {{ name }}_extract
        {%- endfor %}
    from unnest(generate_date_array(
        {{ start_date }},
        date_add(current_date('America/Denver'), interval {{ lookahead_days }} day)
    )) as service_date
    cross join extracts as e
    group by service_date
),
active_services as (
    select
        de.service_date,
        de.trips_extract,
        de.stop_times_extract,
        c.service_id
    from date_extract as de
    join calendar as c
        on c._extract_date = de.calendar_extract
        and de.service_date between c.start_date and c.end_date
        and case extract(dayofweek from de.service_date)
            when 1 then c.sunday
            when 2 then c.monday
            when 3 then c.tuesday
            when 4 then c.wednesday
            when 5 then c.thursday
            when 6 then c.friday
            when 7 then c.saturday
        end
    left join calendar_dates as removed
        on removed._extract_date = de.calendar_dates_extract
        and removed.service_id = c.service_id
        and removed.exception_date = de.service_date
        and removed.exception_type = 2
    where removed.service_id is null

    union distinct

    select
        de.service_date,
        de.trips_extract,
        de.stop_times_extract,
        cd.service_id
    from date_extract as de
    join calendar_dates as cd
        on cd._extract_date = de.calendar_dates_extract
        and cd.exception_date = de.service_date
        and cd.exception_type = 1
),
expanded as (
    select
        a.service_date,
        a.stop_times_extract,
        t.trip_id,
        t.route_id,
        t.direction_id,
        st.stop_id,
        st.stop_sequence,
        case
            when st.arrival_time is not null
                then {{ gtfs_time_to_ts('a.service_date', 'st.arrival_time') }}
        end as sched_arrival_ts_mst,
        case
            when st.departure_time is not null
                then {{ gtfs_time_to_ts('a.service_date', 'st.departure_time') }}
        end as sched_departure_ts_mst
    from active_services as a
    join trips as t
        on t._extract_date = a.trips_extract
        and t.service_id = a.service_id
    join stop_times as st
        on st._extract_date = a.stop_times_extract
        and st.trip_id = t.trip_id
)

select
    e.service_date as service_date_mst,
    e.trip_id,
    e.stop_id,
    e.stop_sequence,
    e.route_id,
    e.direction_id,
    coalesce(dt.trip_key, -1) as trip_key,
    coalesce(dr.route_key, -1) as route_key,
    coalesce(ds.stop_key, -1) as stop_key,
    e.sched_arrival_ts_mst,
    e.sched_departure_ts_mst,
    e.stop_times_extract as gtfs_extract_date
from expanded as e
left join {{ ref('dim_trip') }} as dt
    on dt.trip_id = e.trip_id
    and e.service_date between dt.valid_from and dt.valid_to
left join {{ ref('dim_route') }} as dr
    on dr.route_id = e.route_id
    and e.service_date between dr.valid_from and dr.valid_to
left join {{ ref('dim_stop') }} as ds
    on ds.stop_id = e.stop_id
    and e.service_date between ds.valid_from and ds.valid_to
where e.sched_arrival_ts_mst is not null or e.sched_departure_ts_mst is not null
