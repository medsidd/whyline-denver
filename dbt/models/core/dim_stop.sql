{{ config(cluster_by=['stop_id']) }}

{# Type 2 over GTFS extracts; facts resolve the version valid on their service date #}
with versions as (
    {{ scd2_from_extracts(ref('stg_gtfs_stops'), 'stop_id',
        ['stop_name', 'stop_lat', 'stop_lon', 'wheelchair_boarding'], 'stop_key') }}
)

select
    stop_key,
    stop_id,
    stop_name,
    stop_lat as lat,
    stop_lon as lon,
    {{ make_point('stop_lon', 'stop_lat') }} as geom,
    wheelchair_boarding,
    valid_from,
    valid_to,
    is_current,
    is_latest_version
from versions
union all
select
    -1, cast(null as string), 'Unknown stop', cast(null as float64), cast(null as float64),
    cast(null as geography), cast(null as int64), date '1900-01-01', date '9999-12-31', false, false
