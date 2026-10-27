{{ config(cluster_by=['route_id']) }}

{# Type 2 over GTFS extracts; the -1 member covers events without a route #}
with versions as (
    {{ scd2_from_extracts('(select * from ' ~ ref('stg_gtfs_routes') ~ ' where is_valid)', 'route_id',
        ['route_name', 'route_long_name', 'route_type', 'route_desc'], 'route_key') }}
)

select
    route_key,
    route_id,
    route_name,
    route_long_name,
    route_type,
    route_desc,
    valid_from,
    valid_to,
    is_current,
    is_latest_version
from versions
union all
select
    -1, cast(null as string), 'Unassigned', cast(null as string), cast(null as string),
    cast(null as string), date '1900-01-01', date '9999-12-31', false, false
