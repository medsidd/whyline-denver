{{ config(materialized='view') }}

{#
Every GTFS extract. Filter on `_extract_date` with a constant (see latest_extract_date) so
BigQuery prunes partitions; the window below partitions by it, so the filter pushes down.
#}
select
    _extract_date,
    trip_id,
    stop_id,
    stop_sequence,
    nullif(arrival_time, '') as arrival_time,
    nullif(departure_time, '') as departure_time
from {{ source('raw', 'raw_gtfs_stop_times') }}
qualify row_number() over (
    partition by _extract_date, trip_id, stop_id, stop_sequence
    order by arrival_time
) = 1
