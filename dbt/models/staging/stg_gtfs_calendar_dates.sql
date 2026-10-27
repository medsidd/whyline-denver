{{ config(materialized='view') }}

{# Every GTFS extract; exception_type 1 adds service on a date, 2 removes it; is_valid: date parses and type is 1 or 2 #}
select distinct
    _extract_date,
    service_id,
    safe.parse_date('%Y%m%d', date) as exception_date,
    exception_type,
    coalesce(safe.parse_date('%Y%m%d', date) is not null and exception_type in (1, 2), false) as is_valid
from {{ source('raw', 'raw_gtfs_calendar_dates') }}
