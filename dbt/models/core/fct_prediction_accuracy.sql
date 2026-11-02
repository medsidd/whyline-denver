{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date', 'data_type': 'date'},
    cluster_by=['route_id', 'stop_id'],
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Arrival-prediction accuracy: for each stop visit timed from a shape crossing to within 30 s, the
prediction riders saw 1, 3, 5, 10, 15, 20 and 30 minutes before the vehicle actually arrived. That is
the latest stop-level prediction change at or before that moment; if it was a drop, or nothing
had been predicted yet, no prediction was on screen.

error_sec = actual - predicted: positive means the vehicle came later than predicted (a longer
wait), negative means earlier (a rider trusting the prediction could miss it). Buckets and bands
follow the MBTA's published standard: the bucket is the countdown shown (predicted - as of), and
a prediction is accurate within 1 min early to 1 min late at 0-3 min, 1.5/2 at 3-6, 2.5/3.5 at
6-12 and 4/6 at 12-30.

Raw prediction history expires after 90 days, so full refresh is disabled. Nightly runs replace
the last prediction_accuracy_days complete service dates; the first build starts at the stream.
#}
{% set days = var('prediction_accuracy_days', 3) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('prediction_accuracy_start', '2026-10-29') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with visits as (
    select
        service_date,
        trip_id,
        stop_sequence,
        stop_id,
        route_id,
        direction_id,
        arrival_method,
        arrival_ts_utc
    from {{ ref('fct_stop_visit') }}
    where
        service_date between {{ first }} and {{ last }}
        and arrival_method in ('shape_crossing', 'shape_crossing_gap')
        and within_30s
        and arrival_ts_utc is not null
),
horizons as (
    select horizon_min from unnest([1, 3, 5, 10, 15, 20, 30]) as horizon_min
),
targets as (
    select
        v.*,
        h.horizon_min,
        timestamp_sub(v.arrival_ts_utc, interval h.horizon_min minute) as as_of_ts
    from visits as v
    cross join horizons as h
),
changes as (
    select
        service_date,
        trip_id,
        stop_sequence,
        feed_ts_utc,
        change_type,
        predicted_ts_utc
    from {{ ref('stg_rt_prediction_changes') }}
    where
        not is_trip_level
        -- Constant bounds so BigQuery prunes the raw partitions. A service day runs from about
        -- 10:00 UTC to 10:00 UTC the next day; predictions start a few hours before a trip.
        and feed_ts_utc >= timestamp({{ first }})
        and feed_ts_utc < timestamp(date_add({{ last }}, interval 2 day))
),
as_of as (
    select
        t.*,
        c.change_type,
        c.predicted_ts_utc,
        c.feed_ts_utc as prediction_made_ts
    from targets as t
    left join changes as c
        on c.service_date = t.service_date
        and c.trip_id = t.trip_id
        and c.stop_sequence = t.stop_sequence
        and c.feed_ts_utc <= t.as_of_ts
    qualify row_number() over (
        partition by t.service_date, t.trip_id, t.stop_sequence, t.horizon_min
        order by c.feed_ts_utc desc
    ) = 1
),
predicted as (
    select
        *,
        coalesce(change_type, 'dropped') != 'dropped' as has_prediction
    from as_of
),
scored as (
    select
        *,
        if(has_prediction, timestamp_diff(predicted_ts_utc, as_of_ts, second), null) as countdown_sec,
        if(has_prediction, timestamp_diff(arrival_ts_utc, predicted_ts_utc, second), null) as error_sec
    from predicted
),
bucketed as (
    select
        *,
        -- With no prediction on screen, bucket by the true time to arrival instead.
        case
            when coalesce(countdown_sec, horizon_min * 60) < 180 then '0-3'
            when coalesce(countdown_sec, horizon_min * 60) < 360 then '3-6'
            when coalesce(countdown_sec, horizon_min * 60) < 720 then '6-12'
            else '12-30'
        end as horizon_bucket
    from scored
)

select
    service_date,
    trip_id,
    stop_sequence,
    stop_id,
    route_id,
    direction_id,
    horizon_min,
    horizon_bucket,
    has_prediction,
    if(has_prediction, prediction_made_ts, null) as prediction_made_ts,
    if(has_prediction, predicted_ts_utc, null) as predicted_arrival_ts,
    arrival_ts_utc as actual_arrival_ts,
    arrival_method,
    countdown_sec,
    error_sec,
    case horizon_bucket
        when '0-3' then error_sec between -60 and 60
        when '3-6' then error_sec between -90 and 120
        when '6-12' then error_sec between -150 and 210
        else error_sec between -240 and 360
    end as within_band
from bucketed
