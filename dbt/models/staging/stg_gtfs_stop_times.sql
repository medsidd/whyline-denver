{{ config(materialized='view') }}

{#
Every GTFS extract. Filter on `_extract_date` with a constant (see recent_extracts_filter) so
BigQuery prunes partitions; the window below partitions by it, so the filter pushes down.
is_valid: times must be H:MM:SS (or empty) and stop_sequence present. shape_dist_traveled is
metres along the trip's shape (populated in current feeds, empty in some 2025 feeds).
#}
select
    _extract_date,
    trip_id,
    stop_id,
    stop_sequence,
    nullif(arrival_time, '') as arrival_time,
    nullif(departure_time, '') as departure_time,
    shape_dist_traveled,
    coalesce(
        stop_sequence is not null
        and regexp_contains(coalesce(arrival_time, ''), r'^([0-9]{1,2}:[0-9]{2}:[0-9]{2})?$')
        and regexp_contains(coalesce(departure_time, ''), r'^([0-9]{1,2}:[0-9]{2}:[0-9]{2})?$'),
        false
    ) as is_valid
from {{ source('raw', 'raw_gtfs_stop_times') }}
qualify row_number() over (
    partition by _extract_date, trip_id, stop_id, stop_sequence
    order by is_valid desc, arrival_time
) = 1
