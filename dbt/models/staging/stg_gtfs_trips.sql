{{ config(materialized='view') }}

with cal as (
    select
        service_id,
        start_date,
        end_date,
        monday,
        tuesday,
        wednesday,
        thursday,
        friday,
        saturday,
        sunday
    from {{ source('raw','raw_gtfs_calendar') }}
),
ex as (
    select
        service_id,
        array_agg(case when exception_type = 1 then date end ignore nulls) as added_service_dates,
        array_agg(case when exception_type = 2 then date end ignore nulls) as removed_service_dates
    from {{ source('raw','raw_gtfs_calendar_dates') }}
    group by service_id
),
tr as (
    select
        trip_id,
        route_id,
        service_id,
        direction_id,
        shape_id,
        trip_headsign
    from {{ source('raw','raw_gtfs_trips') }}
)
select
    tr.trip_id,
    tr.route_id,
    tr.service_id,
    tr.direction_id,
    tr.shape_id,
    tr.trip_headsign,
    cal.start_date,
    cal.end_date,
    cal.monday,
    cal.tuesday,
    cal.wednesday,
    cal.thursday,
    cal.friday,
    cal.saturday,
    cal.sunday,
    ex.added_service_dates,
    ex.removed_service_dates
from tr
left join cal using (service_id)
left join ex using (service_id)
