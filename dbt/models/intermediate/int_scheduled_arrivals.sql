{{ config(materialized='view') }}

{#
GTFS schedule data is static and does not grow over time like realtime data.
No date filtering needed - the entire schedule dataset is scanned, but it's relatively small.
#}

with st as (
    select
        trip_id,
        stop_id,
        stop_sequence,
        nullif(arrival_time, '') as arrival_time,
        nullif(departure_time, '') as departure_time
    from {{ ref('stg_gtfs_stop_times') }}
),
tr as (
    select
        trip_id,
        route_id,
        direction_id,
        case
            when start_date is null or start_date = '' then null
            else parse_date('%Y%m%d', start_date)
        end as service_start_date
    from {{ ref('stg_gtfs_trips') }}
),
joined as (
    select
        st.trip_id,
        st.stop_id,
        st.stop_sequence,
        tr.route_id,
        tr.direction_id,
        case
            when st.arrival_time is not null and tr.service_start_date is not null then
                {{ gtfs_time_to_ts("tr.service_start_date", "st.arrival_time") }}
        end as sched_arrival_ts_mst,
        case
            when st.departure_time is not null and tr.service_start_date is not null then
                {{ gtfs_time_to_ts("tr.service_start_date", "st.departure_time") }}
        end as sched_departure_ts_mst
    from st
    join tr
        on st.trip_id = tr.trip_id
)

select
    trip_id,
    stop_id,
    stop_sequence,
    route_id,
    direction_id,
    sched_arrival_ts_mst,
    sched_departure_ts_mst,
    {{ date_mst('coalesce(sched_arrival_ts_mst, sched_departure_ts_mst)') }} as service_date_mst
from joined
