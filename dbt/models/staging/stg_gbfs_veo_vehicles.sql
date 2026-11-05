{{ config(materialized='view') }}

{#
Silver: Veo vehicles per 15-minute snapshot. Filter snapshot_ts_utc with a constant so BigQuery
prunes the raw partitions (30-day expiry). available = neither reserved nor disabled.
#}
select
    snapshot_ts_utc,
    vehicle_type_id,
    form_factor,
    propulsion,
    lat,
    lon,
    {{ make_point('lon', 'lat') }} as geom,
    not coalesce(is_reserved, false) and not coalesce(is_disabled, false) as is_available,
    current_range_m
from {{ source('raw', 'raw_gbfs_veo_vehicles') }}
where lat is not null and lon is not null
