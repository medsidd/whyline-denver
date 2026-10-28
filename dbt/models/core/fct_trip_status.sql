{#
Grain: one trip instance (service date x trip_id) as the poller closed it: final trip
relationship, outcome (completed, partial, vanished, canceled, no_static), first and last seen,
and visit counts by method. Lets marts report cancellations and vanished trips instead of
counting them as missing visits. Insert-only, like fct_stop_visit, and kept permanently.
#}
{% set service_bound = "service_date >= date_sub(current_date('America/Denver'), interval " ~ var('stop_visit_service_days', 1) ~ " day)" %}
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['service_date', 'trip_id'],
        partition_by={'field': 'service_date', 'data_type': 'date'},
        cluster_by=['route_id'],
        incremental_predicates=['DBT_INTERNAL_DEST.' ~ service_bound],
        on_schema_change='append_new_columns',
        full_refresh=false
    )
}}

with batch as (
    select *
    from {{ ref('stg_rt_trip_status') }}
    where {{ service_bound }}
    {% if is_incremental() %}
      and _ingested_at >= timestamp_sub(current_timestamp(), interval {{ var('stop_visit_lookback_hours', 6) }} hour)
    {% endif %}
    qualify row_number() over (
        partition by service_date, trip_id order by closed_at desc, _ingested_at desc
    ) = 1
),
new_trips as (
    select b.*
    from batch as b
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} as f
        where f.{{ service_bound }}
          and f.service_date = b.service_date
          and f.trip_id = b.trip_id
    )
    {% endif %}
)

select
    t.service_date,
    t.trip_id,
    coalesce(dt.trip_key, -1) as trip_key,
    coalesce(dr.route_key, -1) as route_key,
    t.route_id,
    t.direction_id,
    t.final_schedule_relationship,
    t.outcome,
    t.first_seen_ts,
    t.last_seen_ts,
    t.first_vp_ts,
    t.last_vp_ts,
    t.had_vehicle,
    t.n_stops_static,
    t.n_visits,
    t.n_shape_crossing,
    t.n_last_prediction,
    t.n_skipped,
    t.data_version,
    t.static_md5,
    t._ingested_at
from new_trips as t
left join {{ ref('dim_trip') }} as dt
    on dt.trip_id = t.trip_id
    and t.service_date between dt.valid_from and dt.valid_to
left join {{ ref('dim_route') }} as dr
    on dr.route_id = t.route_id
    and t.service_date between dr.valid_from and dr.valid_to
