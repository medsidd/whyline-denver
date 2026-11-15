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
-- A snapshot file loaded twice (two loaders at once, before the loader lock) would count every
-- vehicle twice, and vehicles carry no ID to deduplicate on; keep the first load of each file.
qualify _ingested_at = min(_ingested_at) over (partition by _source_path)
