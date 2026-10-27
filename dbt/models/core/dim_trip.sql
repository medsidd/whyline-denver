{{ config(cluster_by=['trip_id']) }}

{# Type 2 over GTFS extracts #}
with versions as (
    {{ scd2_from_extracts('(select * from ' ~ ref('stg_gtfs_trips') ~ ' where is_valid)', 'trip_id',
        ['route_id', 'service_id', 'direction_id', 'trip_headsign', 'shape_id'], 'trip_key') }}
)

select
    trip_key,
    trip_id,
    route_id,
    service_id,
    direction_id,
    trip_headsign,
    shape_id,
    valid_from,
    valid_to,
    is_current,
    is_latest_version
from versions
union all
select
    -1, cast(null as string), cast(null as string), cast(null as string), cast(null as int64),
    'Unknown trip', cast(null as string), date '1900-01-01', date '9999-12-31', false, false
