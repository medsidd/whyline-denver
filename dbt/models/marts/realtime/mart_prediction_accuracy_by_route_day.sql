{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": false}
) }}

{#
How far arrival predictions were off, per route, day and how far ahead they were shown.
error_sec = actual - predicted (positive: the vehicle came later than predicted). Published in
the app after the stop-visit dual-run review; until then allow_in_app is false.
#}
{% set days = var('prediction_accuracy_days', 3) %}

select
    route_id,
    service_date as service_date_mst,
    horizon_bucket,
    count(*) as n_visits,
    countif(has_prediction) as n_predictions,
    countif(not has_prediction) as n_no_prediction,
    avg(if(has_prediction, if(within_band, 1, 0), null)) as pct_within_band,
    approx_quantiles(error_sec, 100)[offset(50)] as median_error_sec,
    approx_quantiles(error_sec, 100)[offset(5)] as p05_error_sec,
    approx_quantiles(error_sec, 100)[offset(95)] as p95_error_sec,
    -- Extra minutes a rider must allow to avoid missing a vehicle that comes early.
    greatest(0, -approx_quantiles(error_sec, 100)[offset(5)]) as padding_sec,
    avg(if(has_prediction, if(error_sec > 120, 1, 0), null)) as pct_later_by_2min,
    avg(if(has_prediction, if(error_sec < -60, 1, 0), null)) as pct_earlier_by_1min,
    current_timestamp() as build_run_at
from {{ ref('fct_prediction_accuracy') }}
where route_id is not null
{% if is_incremental() %}
    and service_date >= date_sub(current_date('America/Denver'), interval {{ days }} day)
{% endif %}
group by 1, 2, 3
