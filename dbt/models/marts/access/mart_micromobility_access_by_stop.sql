{{ config(materialized='table', cluster_by=['stop_id'], meta={"allow_in_app": false}) }}

{#
First and last mile: how many Veo scooters and bikes are usually available within 200 m of each
Denver stop, and how often there are none, by weekday or weekend and period, over the last
micromobility_window_days local dates, today included. Goes into the app with the next release.
#}
{% set window_days = var('micromobility_window_days', 28) %}

with hours as (
    select
        *,
        if(format_date('%u', date_mst) in ('6', '7'), 'weekend', 'weekday') as day_type,
        case
            when hour_mst between 4 and 6 then 'early'
            when hour_mst between 7 and 8 then 'am_peak'
            when hour_mst between 9 and 14 then 'midday'
            when hour_mst between 15 and 17 then 'pm_peak'
            when hour_mst between 18 and 20 then 'evening'
            else 'night'
        end as period
    from {{ ref('fct_micromobility_near_stop') }}
    where date_mst between date_sub(current_date('America/Denver'), interval {{ window_days - 1 }} day)
        and current_date('America/Denver')
)

select
    h.stop_id,
    any_value(st.stop_name) as stop_name,
    any_value(st.lat) as lat,
    any_value(st.lon) as lon,
    h.day_type,
    h.period,
    count(distinct h.date_mst) as n_days,
    round(safe_divide(sum(if(h.form_factor = 'scooter', h.avg_available_within_200m * h.n_snapshots, 0)),
        sum(if(h.form_factor = 'scooter', h.n_snapshots, 0))), 2) as avg_scooters_within_200m,
    round(safe_divide(sum(if(h.form_factor = 'bicycle', h.avg_available_within_200m * h.n_snapshots, 0)),
        sum(if(h.form_factor = 'bicycle', h.n_snapshots, 0))), 2) as avg_bikes_within_200m,
    safe_divide(sum(if(h.form_factor = 'scooter', h.pct_snapshots_none_within_200m * h.n_snapshots, 0)),
        sum(if(h.form_factor = 'scooter', h.n_snapshots, 0))) as pct_time_no_scooter,
    safe_divide(sum(if(h.form_factor = 'bicycle', h.pct_snapshots_none_within_200m * h.n_snapshots, 0)),
        sum(if(h.form_factor = 'bicycle', h.n_snapshots, 0))) as pct_time_no_bike,
    current_timestamp() as build_run_at
from hours as h
left join {{ ref('dim_stop') }} as st
    on st.stop_id = h.stop_id
    and st.is_current
group by h.stop_id, h.day_type, h.period
