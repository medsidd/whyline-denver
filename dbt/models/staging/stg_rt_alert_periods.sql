{{ config(materialized='view') }}

{# Silver: active periods per alert per snapshot; a NULL start or end is open. Filter feed_ts_utc with a constant. #}
select
    feed_ts_utc,
    alert_id,
    active_start_utc,
    active_end_utc
from {{ source('raw', 'raw_gtfsrt_alert_periods') }}
where alert_id is not null
