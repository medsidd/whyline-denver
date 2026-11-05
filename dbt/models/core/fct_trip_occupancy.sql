{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date', 'data_type': 'date'},
    cluster_by=['route_id', 'stop_id'],
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Crowding: the highest occupancy RTD reported on the way to, or at, each stop of each trip. One
row per stop visit; stops with no report keep n_reports = 0. A vehicle report counts toward its
stop_id, at the first occurrence at or ahead of the vehicle's progress along the shape (50 m
slack, as the poller uses), so loop routes that pass a stop twice resolve.

Levels: 1 many seats (or empty), 2 few seats, 3 standing room only, 4 crushed standing room
only, 5 full. NO_DATA_AVAILABLE and missing values are no data. Only some vehicles report, and
RTD sets the thresholds. Raw reports expire after 90 days, so full refresh is disabled.
#}
{% set days = var('crowding_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('crowding_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with visits as (
    select
        service_date,
        trip_id,
        stop_sequence,
        stop_id,
        stop_role,
        route_id,
        direction_id,
        stop_dist_m,
        -- The first stop's arrival holds its departure; skipped stops fall back to the schedule.
        coalesce(arrival_ts_utc, scheduled_arrival_ts) as event_ts_utc
    from {{ ref('fct_stop_visit') }}
    where service_date between {{ first }} and {{ last }}
),
reports as (
    select
        service_date,
        trip_id,
        vehicle_id,
        report_ts_utc,
        stop_id,
        dist_along_m,
        case occupancy_status
            when 'EMPTY' then 1
            when 'MANY_SEATS_AVAILABLE' then 1
            when 'FEW_SEATS_AVAILABLE' then 2
            when 'STANDING_ROOM_ONLY' then 3
            when 'CRUSHED_STANDING_ROOM_ONLY' then 4
            when 'FULL' then 5
        end as level
    from {{ ref('stg_rt_vehicle_positions') }}
    where
        -- Constant bounds so BigQuery prunes the raw partitions (see fct_prediction_accuracy).
        feed_ts_utc >= timestamp({{ first }})
        and feed_ts_utc < timestamp(date_add({{ last }}, interval 2 day))
        and valid_for_timing
        and stop_id is not null
),
matched as (
    select
        r.service_date,
        r.trip_id,
        v.stop_sequence,
        r.report_ts_utc,
        r.level
    from reports as r
    join visits as v
        on v.service_date = r.service_date
        and v.trip_id = r.trip_id
        and v.stop_id = r.stop_id
        and v.stop_dist_m >= r.dist_along_m - 50
    qualify row_number() over (
        partition by r.service_date, r.trip_id, r.vehicle_id, r.report_ts_utc
        order by v.stop_sequence
    ) = 1
),
by_stop as (
    select
        service_date,
        trip_id,
        stop_sequence,
        count(*) as n_reports,
        countif(level is not null) as n_reports_with_data,
        max(level) as max_level,
        min(report_ts_utc) as first_report_ts
    from matched
    group by 1, 2, 3
)

select
    v.service_date,
    v.trip_id,
    v.stop_sequence,
    v.stop_id,
    v.stop_role,
    v.route_id,
    v.direction_id,
    v.event_ts_utc,
    coalesce(b.n_reports, 0) as n_reports,
    coalesce(b.n_reports_with_data, 0) as n_reports_with_data,
    b.max_level,
    case b.max_level
        when 1 then 'many_seats'
        when 2 then 'few_seats'
        when 3 then 'standing_room_only'
        when 4 then 'crushed_standing_room_only'
        when 5 then 'full'
    end as max_level_label,
    b.first_report_ts
from visits as v
left join by_stop as b
    on b.service_date = v.service_date
    and b.trip_id = v.trip_id
    and b.stop_sequence = v.stop_sequence
