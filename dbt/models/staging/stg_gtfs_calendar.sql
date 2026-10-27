{{ config(materialized='view') }}

{# Every GTFS extract; is_valid: both service-period dates parse #}
select
    _extract_date,
    service_id,
    safe.parse_date('%Y%m%d', start_date) as start_date,
    safe.parse_date('%Y%m%d', end_date) as end_date,
    monday = 1 as monday,
    tuesday = 1 as tuesday,
    wednesday = 1 as wednesday,
    thursday = 1 as thursday,
    friday = 1 as friday,
    saturday = 1 as saturday,
    sunday = 1 as sunday,
    safe.parse_date('%Y%m%d', start_date) is not null
        and safe.parse_date('%Y%m%d', end_date) is not null as is_valid
from {{ source('raw', 'raw_gtfs_calendar') }}
qualify row_number() over (
    partition by _extract_date, service_id
    order by is_valid desc, start_date, end_date
) = 1
