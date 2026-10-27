{{ config(materialized='view') }}

{# Every GTFS extract; exception_type 1 adds service on a date, 2 removes it #}
select distinct
    _extract_date,
    service_id,
    safe.parse_date('%Y%m%d', date) as exception_date,
    exception_type
from {{ source('raw', 'raw_gtfs_calendar_dates') }}
where safe.parse_date('%Y%m%d', date) is not null
