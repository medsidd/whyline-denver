{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
    on_schema_change='append_new_columns',
    meta={"allow_in_app": false}
) }}

{#
Wait time, bunching and gaps per route and service date, over every stop. Excess wait uses only
headways scheduled every 15 minutes or better, where riders don't time their arrival; on-time
share and late running cover every visit. Published after the stop-visit review.
#}
{% set days = var('wait_days', 3) %}

with headways as (
    -- h and s: frequent observed and scheduled headways, kept only where both are known.
    select
        *,
        if(scheduled_headway_sec between 1 and 900, observed_headway_sec, null) as h,
        if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, scheduled_headway_sec, null) as s
    from {{ ref('fct_stop_headway') }}
    {% if is_incremental() %}
    where service_date >= date_sub(current_date('America/Denver'), interval {{ days }} day)
    {% endif %}
)

select
    route_id,
    service_date as service_date_mst,
    count(*) as n_visits,
    count(h) as n_frequent_headways,
    safe_divide(sum(h * h), 2 * sum(h)) as expected_wait_sec,
    safe_divide(sum(s * s), 2 * sum(s)) as scheduled_wait_sec,
    safe_divide(sum(h * h), 2 * sum(h)) - safe_divide(sum(s * s), 2 * sum(s)) as excess_wait_sec,
    avg(if(h is null, null, if(h < 0.25 * s, 1, 0))) as pct_bunched,
    avg(if(h is null, null, if(h > 1.5 * s, 1, 0))) as pct_gap,
    avg(if(
        delay_sec is null, null,
        if(delay_sec > -{{ var('on_time_early_sec', 60) }} and delay_sec <= {{ var('on_time_late_sec', 300) }}, 1, 0)
    )) as pct_on_time,
    approx_quantiles(delay_sec, 10)[offset(9)] as p90_delay_sec,
    current_timestamp() as build_run_at
from headways
group by 1, 2
