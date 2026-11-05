{{ config(materialized='view') }}

{#
Silver: RTD's National Transit Database monthly module rows from the latest extract. Each
extract is the full history, because NTD revises earlier months, so older extracts are ignored.
#}
select
    month,
    mode,
    tos,
    mode_group,
    upt,
    vrm,
    vrh,
    voms
from {{ source('raw', 'raw_ntd_monthly') }}
where _extract_date = {{ latest_extract_date(source('raw', 'raw_ntd_monthly')) }}
qualify row_number() over (partition by month, mode, tos order by _ingested_at desc) = 1
