{{ config(
    materialized='incremental',
    unique_key='headway_event_id',
    on_schema_change='fail',
    partition_by={
        'field': 'service_date_mst',
        'data_type': 'date',
        'granularity': 'day'
    },
    cluster_by=['route_id', 'stop_id'],
    meta={"allow_in_app": false, "layer": "fct"}
) }}

{% set incremental_days = 3 %}

select
    to_hex(sha256(concat(
        cast(route_id as string),
        '|', coalesce(cast(direction_id as string), '__null__'),
        '|', cast(stop_id as string),
        '|', cast(service_date_mst as string),
        '|', cast(event_ts_utc as string)
    )))                 as headway_event_id,
    route_id,
    direction_id,
    stop_id,
    service_date_mst,
    event_ts_utc,
    obs_headway_sec,
    sch_headway_sec,
    dt_abs,
    headway_adherent
from {{ ref('int_headway_adherence') }}
{% if is_incremental() %}
where service_date_mst >= date_sub(current_date('America/Denver'), interval {{ incremental_days }} day)
{% endif %}
