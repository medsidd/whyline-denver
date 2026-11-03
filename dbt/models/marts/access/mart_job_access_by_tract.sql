{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
How many jobs can I reach by transit? Per census tract in the RTD counties and departure
window: jobs reachable within 30, 45 and 60 minutes by walking and transit, as counts and as a
share of the region's jobs. Travel times come from the published schedule, not from what ran;
jobs are LEHD LODES workplace counts. Denver tracts also carry their EnviroScreen percentile.
Published with release R3.
#}
with access as (
    select
        geoid,
        departure_window,
        any_value(departure_date) as departure_date,
        max(if(minutes_threshold = 30, jobs_reachable, null)) as jobs_within_30min,
        max(if(minutes_threshold = 45, jobs_reachable, null)) as jobs_within_45min,
        max(if(minutes_threshold = 60, jobs_reachable, null)) as jobs_within_60min,
        any_value(total_jobs_region) as total_jobs_region,
        any_value(lodes_year) as lodes_year
    from {{ ref('fct_job_access') }}
    group by 1, 2
),
enviroscreen as (
    select
        json_value(properties_json, '$.GEOID') as geoid,
        safe_cast(json_value(properties_json, '$.ES_S_') as float64) as enviroscreen_pctl
    from {{ ref('stg_arcgis_reference') }}
    where layer = 'enviroscreen_tract'
)

select
    a.geoid,
    substr(a.geoid, 3, 3) = '031' as is_denver,
    a.departure_window,
    a.departure_date,
    a.jobs_within_30min,
    a.jobs_within_45min,
    a.jobs_within_60min,
    round(safe_divide(a.jobs_within_45min, a.total_jobs_region), 4) as pct_region_jobs_45min,
    a.total_jobs_region,
    a.lodes_year,
    e.enviroscreen_pctl,
    current_timestamp() as build_run_at
from access as a
left join enviroscreen as e
    using (geoid)
