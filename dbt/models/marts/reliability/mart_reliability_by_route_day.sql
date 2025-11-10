{{ config(
    materialized='incremental',
    unique_key=['route_id', 'service_date_mst', 'precip_bin', 'snow_day'],
    partition_by={"field": "service_date_mst", "data_type": "date"},
    cluster_by=["route_id"],
    meta={"allow_in_app": true}
) }}

with e as (
    select
        route_id,
        service_date_mst,
        delay_sec,
        delay_sec_raw
    from {{ ref('int_rt_events_resolved') }}
    where true
    {% if is_incremental() %}
        and service_date_mst >= date_sub(current_date("America/Denver"), interval 3 day)
    {% endif %}
),
w as (
    select
        service_date_mst,
        precip_bin,
        snow_day
    from {{ ref('int_weather_by_date') }}
)

select
    e.route_id,
    e.service_date_mst,
    coalesce(w.precip_bin, 'none') as precip_bin,
    coalesce(w.snow_day, false) as snow_day,
    count(*) as n_events,
    countif(delay_sec_raw is not null) as n_reported_events,
    avg(case when abs(delay_sec) <= {{ var('on_time_sec', 300) }} then 1 else 0 end) as pct_on_time,
    avg(delay_sec) as mean_delay_sec,
    approx_quantiles(delay_sec, 100)[offset(50)] as median_delay_sec,
    approx_quantiles(delay_sec, 100)[offset(90)] as p90_delay_sec,
    current_timestamp() as build_run_at
from e
left join w
    using (service_date_mst)
group by
    route_id,
    service_date_mst,
    precip_bin,
    snow_day
