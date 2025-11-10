{{
    config(
        materialized='table',
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['trip_id', 'stop_id']
    )
}}

{#
GTFS schedule expansion: Generate scheduled arrivals for all service dates.
This expands trips across their entire service period based on calendar rules.

Cost optimization: Materialized as table to avoid re-expanding schedule on every query.
- Generates ~22M rows (expanding schedule for 76 days)
- Rebuild when GTFS static data is updated or via scheduled refresh
#}

{# Limit expansion to recent/future dates to control data volume #}
{% set lookback_days = var('schedule_expansion_lookback_days', 45) %}
{% set lookahead_days = var('schedule_expansion_lookahead_days', 30) %}

with calendar as (
    select
        service_id,
        case when start_date is null or start_date = '' then null else parse_date('%Y%m%d', start_date) end as start_date,
        case when end_date is null or end_date = '' then null else parse_date('%Y%m%d', end_date) end as end_date,
        monday = 1 as runs_monday,
        tuesday = 1 as runs_tuesday,
        wednesday = 1 as runs_wednesday,
        thursday = 1 as runs_thursday,
        friday = 1 as runs_friday,
        saturday = 1 as runs_saturday,
        sunday = 1 as runs_sunday
    from {{ source('raw', 'raw_gtfs_calendar') }}
    where start_date is not null and start_date != ''
      and end_date is not null and end_date != ''
),
calendar_dates as (
    select
        service_id,
        case when date is null or date = '' then null else parse_date('%Y%m%d', date) end as exception_date,
        exception_type
    from {{ source('raw', 'raw_gtfs_calendar_dates') }}
    where date is not null and date != ''
),
date_spine as (
    -- Generate all dates in the expansion window
    {{ gtfs_date_spine(
        "date_sub(current_date('America/Denver'), interval " ~ lookback_days ~ " day)",
        "date_add(current_date('America/Denver'), interval " ~ lookahead_days ~ " day)"
    ) }}
),
service_dates as (
    -- Cross-join calendar with date spine, filter by service period and day of week
    select
        cal.service_id,
        ds.service_date
    from calendar as cal
    cross join date_spine as ds
    where ds.service_date >= cal.start_date
      and ds.service_date <= cal.end_date
      and (
        -- Filter by day of week based on calendar
        (ds.is_monday and cal.runs_monday)
        or (ds.is_tuesday and cal.runs_tuesday)
        or (ds.is_wednesday and cal.runs_wednesday)
        or (ds.is_thursday and cal.runs_thursday)
        or (ds.is_friday and cal.runs_friday)
        or (ds.is_saturday and cal.runs_saturday)
        or (ds.is_sunday and cal.runs_sunday)
      )
),
service_dates_with_exceptions as (
    select
        sd.service_id,
        sd.service_date
    from service_dates as sd
    left join calendar_dates as cd_remove
        on sd.service_id = cd_remove.service_id
        and sd.service_date = cd_remove.exception_date
        and cd_remove.exception_type = 2  -- Removed service
    where cd_remove.exception_date is null  -- Exclude removed dates

    union distinct

    -- Add exception dates (exception_type = 1)
    select
        service_id,
        exception_date as service_date
    from calendar_dates
    where exception_type = 1
      and exception_date >= date_sub(current_date('America/Denver'), interval {{ lookback_days }} day)
      and exception_date <= date_add(current_date('America/Denver'), interval {{ lookahead_days }} day)
),
trips_expanded as (
    -- Expand trips to all their service dates
    select
        tr.trip_id,
        tr.route_id,
        tr.direction_id,
        sd.service_date
    from {{ ref('stg_gtfs_trips') }} as tr
    join service_dates_with_exceptions as sd
        on tr.service_id = sd.service_id
),
stop_times as (
    select
        trip_id,
        stop_id,
        stop_sequence,
        nullif(arrival_time, '') as arrival_time,
        nullif(departure_time, '') as departure_time
    from {{ ref('stg_gtfs_stop_times') }}
),
joined as (
    select
        te.trip_id,
        st.stop_id,
        st.stop_sequence,
        te.route_id,
        te.direction_id,
        te.service_date,
        case
            when st.arrival_time is not null then
                {{ gtfs_time_to_ts("te.service_date", "st.arrival_time") }}
        end as sched_arrival_ts_mst,
        case
            when st.departure_time is not null then
                {{ gtfs_time_to_ts("te.service_date", "st.departure_time") }}
        end as sched_departure_ts_mst
    from trips_expanded as te
    join stop_times as st
        on te.trip_id = st.trip_id
)

select
    trip_id,
    stop_id,
    stop_sequence,
    route_id,
    direction_id,
    sched_arrival_ts_mst,
    sched_departure_ts_mst,
    service_date as service_date_mst
from joined
where sched_arrival_ts_mst is not null or sched_departure_ts_mst is not null
