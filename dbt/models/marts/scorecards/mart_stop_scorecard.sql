{{ config(materialized='table', cluster_by=['stop_id'], meta={"allow_in_app": false}) }}

{#
"How is my stop doing?" One row per current stop, over the last scorecard_window_days service
dates where a measure is time-based: scheduled service, measured reliability and wait, prediction
accuracy, crowding, safety, access, alerts in effect, equity context and nearby scooters and
bikes. Each measured component comes with its count; a missing component stays NULL, never 0.
Reads the published marts where they already hold the answer. Published with release R4.
#}
{% set window_days = var('scorecard_window_days', 28) %}
{% set since = "date_sub(current_date('America/Denver'), interval " ~ window_days ~ " day)" %}
{% set until = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with stops as (
    select stop_id, stop_name, lat, lon
    from {{ ref('dim_stop') }}
    where is_current
),
service as (
    select
        stop_id,
        string_agg(distinct route_id, ',' order by route_id) as weekday_route_ids,
        sum(n_departures) as weekday_departures
    from {{ ref('mart_service_frequency_by_stop') }}
    where day_type = 'weekday'
    group by 1
),
reliability as (
    select
        stop_id,
        count(*) as n_visits_measured,
        avg(if(delay_sec is null, null,
            if(delay_sec > -{{ var('on_time_early_sec', 60) }} and delay_sec <= {{ var('on_time_late_sec', 300) }}, 1, 0))) as pct_on_time,
        safe_divide(
            sum(if(scheduled_headway_sec between 1 and 900, pow(observed_headway_sec, 2), null)),
            2 * sum(if(scheduled_headway_sec between 1 and 900, observed_headway_sec, null))
        ) - safe_divide(
            sum(if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, pow(scheduled_headway_sec, 2), null)),
            2 * sum(if(observed_headway_sec is not null and scheduled_headway_sec between 1 and 900, scheduled_headway_sec, null))
        ) as excess_wait_sec,
        avg(if(observed_headway_sec is null or not scheduled_headway_sec between 1 and 900, null,
            if(observed_headway_sec < 0.25 * scheduled_headway_sec, 1, 0))) as pct_bunched
    from {{ ref('fct_stop_headway') }}
    where service_date between {{ since }} and {{ until }}
    group by 1
),
predictions as (
    select
        stop_id,
        countif(has_prediction and horizon_bucket = '0-3') as n_predictions_0_3,
        avg(if(has_prediction and horizon_bucket = '0-3', if(within_band, 1, 0), null)) as pct_predictions_accurate_0_3,
        avg(if(has_prediction and horizon_bucket = '6-12', if(within_band, 1, 0), null)) as pct_predictions_accurate_6_12
    from {{ ref('fct_prediction_accuracy') }}
    where service_date between {{ since }} and {{ until }}
    group by 1
),
crowding as (
    select
        stop_id,
        countif(max_level is not null) as n_visits_with_occupancy,
        avg(if(max_level is null, null, if(max_level >= 3, 1, 0))) as pct_arrivals_standing_or_worse
    from {{ ref('fct_trip_occupancy') }}
    where service_date between {{ since }} and {{ until }}
    group by 1
),
alerts as (
    select stop_id, countif(is_active_now) as n_alerts_in_effect, countif(is_active_now and is_closure) as n_closures_in_effect
    from {{ ref('mart_stop_closures') }}
    group by 1
),
jobs as (
    -- Population-weighted over the Denver tracts within 804.672 m (bridge_stop_tract).
    select b.stop_id, round(sum(cast(b.weighting_factor as float64) * j.jobs_reachable)) as jobs_within_45min_am_peak
    from {{ ref('bridge_stop_tract') }} as b
    join {{ ref('fct_job_access') }} as j
        on j.geoid = b.geoid
        and j.departure_window = 'weekday_am_peak'
        and j.minutes_threshold = 45
    group by 1
),
micromobility as (
    select
        stop_id,
        round(avg(if(form_factor = 'scooter', avg_available_within_200m, null)), 2) as avg_scooters_within_200m,
        round(avg(if(form_factor = 'bicycle', avg_available_within_200m, null)), 2) as avg_bikes_within_200m
    from {{ ref('fct_micromobility_near_stop') }}
    where date_mst between {{ since }} and {{ until }}
    group by 1
)

select
    s.stop_id,
    s.stop_name,
    s.lat,
    s.lon,
    sv.weekday_route_ids,
    sv.weekday_departures,
    r.n_visits_measured,
    r.pct_on_time,
    r.excess_wait_sec,
    r.pct_bunched,
    p.n_predictions_0_3,
    p.pct_predictions_accurate_0_3,
    p.pct_predictions_accurate_6_12,
    c.n_visits_with_occupancy,
    c.pct_arrivals_standing_or_worse,
    cr.crash_250m_cnt,
    cr.ped_crash_250m_cnt,
    cr.ped_bike_severe_250m_cnt,
    ws.on_hin,
    ws.walk_safety_flags,
    ac.access_score_0_100,
    ac.wheelchair_boarding,
    coalesce(al.n_alerts_in_effect, 0) as n_alerts_in_effect,
    coalesce(al.n_closures_in_effect, 0) as n_closures_in_effect,
    v.vuln_score_0_100,
    v.enviroscreen_pctl,
    v.is_disproportionately_impacted,
    v.doti_equity_group_rank,
    m.avg_scooters_within_200m,
    m.avg_bikes_within_200m,
    jb.jobs_within_45min_am_peak,
    current_timestamp() as build_run_at
from stops as s
left join service as sv using (stop_id)
left join reliability as r using (stop_id)
left join predictions as p using (stop_id)
left join crowding as c using (stop_id)
left join {{ ref('mart_crash_proximity_by_stop') }} as cr using (stop_id)
left join {{ ref('mart_stop_walk_safety') }} as ws using (stop_id)
left join {{ ref('mart_access_score_by_stop') }} as ac using (stop_id)
left join alerts as al using (stop_id)
left join {{ ref('mart_vulnerability_by_stop') }} as v using (stop_id)
left join micromobility as m using (stop_id)
left join jobs as jb using (stop_id)
