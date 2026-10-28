{#
Grain: one stop visit per service date x trip x stop_sequence, kept permanently (raw expires
after 90 days, so full refreshes are disabled). The poller emits only final visits, so this is
insert-only: each run takes rows loaded in the last stop_visit_lookback_hours (raw is
partitioned by load hour) and drops keys the fact already holds. The anti-join reads key
columns only and the MERGE then matches nothing, so no partition is rewritten.
Normal runs merge service dates from yesterday to today (Denver), which is what the poller
finalizes; older rows wait in raw for a run with a wider stop_visit_service_days.
The one-off backfill load runs with stop_visit_backfill=true and stream_start_date set.
Service date comes from GTFS start_date, so trips past midnight belong to the day they began.
#}
{% set backfill = var('stop_visit_backfill', false) %}
{% set stream_start = var('stream_start_date', '2100-01-01') %}
{% set service_days = var('stop_visit_service_days', 1) %}
{% if backfill %}
    {% set service_bound = "service_date < date '" ~ stream_start ~ "'" %}
{% else %}
    {% set service_bound = "service_date >= date_sub(current_date('America/Denver'), interval " ~ service_days ~ " day)" %}
{% endif %}
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['service_date', 'trip_id', 'stop_sequence'],
        partition_by={'field': 'service_date', 'data_type': 'date'},
        cluster_by=['route_id', 'stop_id'],
        incremental_predicates=['DBT_INTERNAL_DEST.' ~ service_bound],
        on_schema_change='append_new_columns',
        full_refresh=false
    )
}}

with batch as (
    select *
    from {{ ref('stg_rt_stop_visits') }}
    where {{ service_bound }}
    {% if backfill %}
      and data_version = 'backfill_v1'
    {% else %}
      and data_version != 'backfill_v1'
      {% if is_incremental() %}
      and _ingested_at >= timestamp_sub(current_timestamp(), interval {{ var('stop_visit_lookback_hours', 6) }} hour)
      {% endif %}
    {% endif %}
    qualify row_number() over (
        partition by service_date, trip_id, stop_sequence
        order by emitted_at desc, _ingested_at desc
    ) = 1
),
new_visits as (
    select b.*
    from batch as b
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} as f
        where f.{{ service_bound }}
          and f.service_date = b.service_date
          and f.trip_id = b.trip_id
          and f.stop_sequence = b.stop_sequence
    )
    {% endif %}
),
schedule as (
    -- Same service-date bound as the batch, so BigQuery prunes the schedule partitions.
    select
        service_date_mst as service_date,
        trip_id,
        stop_sequence,
        stop_id,
        route_id,
        direction_id,
        trip_key,
        route_key,
        stop_key,
        sched_arrival_ts_mst,
        sched_departure_ts_mst,
        timestamp_diff(
            coalesce(sched_arrival_ts_mst, sched_departure_ts_mst),
            lag(coalesce(sched_arrival_ts_mst, sched_departure_ts_mst)) over (
                partition by service_date_mst, route_id, direction_id, stop_id
                order by coalesce(sched_arrival_ts_mst, sched_departure_ts_mst), trip_id
            ),
            second
        ) as scheduled_headway_sec
    from {{ ref('fct_scheduled_stop_time') }}
    where {{ service_bound | replace('service_date', 'service_date_mst') }}
      and service_date_mst <= current_date('America/Denver')
),
conformed as (
    select
        v.*,
        s.trip_key,
        s.route_key,
        s.stop_key,
        s.sched_arrival_ts_mst as scheduled_arrival_ts,
        s.sched_departure_ts_mst as scheduled_departure_ts,
        s.scheduled_headway_sec,
        -- The origin's event is its departure; elsewhere, the arrival.
        if(
            v.stop_role = 'first',
            coalesce(s.sched_departure_ts_mst, s.sched_arrival_ts_mst),
            coalesce(s.sched_arrival_ts_mst, s.sched_departure_ts_mst)
        ) as scheduled_event_ts
    from new_visits as v
    left join schedule as s
        on s.service_date = v.service_date
        and s.trip_id = v.trip_id
        and s.stop_sequence = v.stop_sequence
)

select
    farm_fingerprint(concat(
        cast(service_date as string), '|', trip_id, '|', cast(stop_sequence as string)
    )) as stop_visit_key,
    service_date,
    trip_id,
    stop_sequence,
    stop_id,
    stop_role,
    route_id,
    direction_id,
    trip_headsign,
    vehicle_id,
    coalesce(trip_key, -1) as trip_key,
    coalesce(route_key, -1) as route_key,
    coalesce(stop_key, -1) as stop_key,
    arrival_ts_utc,
    arrival_earliest_ts,
    arrival_latest_ts,
    {{ as_mst('arrival_ts_utc') }} as arrival_ts_mst,
    {{ hour_mst('arrival_ts_utc') }} as arrival_hour_mst,
    departure_earliest_ts,
    departure_latest_ts,
    dwell_min_sec,
    dwell_max_sec,
    arrival_method,
    timestamp_diff(arrival_latest_ts, arrival_earliest_ts, second) as arrival_window_sec,
    timestamp_diff(arrival_latest_ts, arrival_earliest_ts, second) <= 30 as within_30s,
    scheduled_arrival_ts,
    scheduled_departure_ts,
    scheduled_headway_sec,
    -- NULL when either side is unknown; marts exclude unknown delays from on-time shares.
    timestamp_diff(arrival_ts_utc, scheduled_event_ts, second) as delay_sec,
    skipped,
    stopped_observed,
    before_report_ts,
    before_dist_along_m,
    after_report_ts,
    after_dist_along_m,
    stop_dist_m,
    nearest_offset_m,
    last_predicted_arrival_ts,
    last_prediction_published_ts,
    if(
        arrival_method like '%crossing%' or arrival_method = 'origin_departure',
        timestamp_diff(last_predicted_arrival_ts, arrival_ts_utc, second),
        null
    ) as prediction_error_sec,
    trip_switch_at_terminal,
    low_confidence,
    is_final,
    data_version,
    static_md5,
    _ingested_at
from conformed
