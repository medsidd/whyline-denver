{{ config(materialized='view') }}

{#
Silver: RTD's own monthly figures from its Bus and Rail Operations reports, from the latest
extract (each is the full history of linked reports).
#}
select
    report_month,
    mode,
    service,
    metric,
    value_pct,
    source_url
from {{ source('raw', 'raw_rtd_reported_performance') }}
where _extract_date = {{ latest_extract_date(source('raw', 'raw_rtd_reported_performance')) }}
qualify row_number() over (partition by report_month, mode, service, metric order by _ingested_at desc) = 1
