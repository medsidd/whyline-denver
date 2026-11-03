{#
Grain: one origin tract x departure window x travel-time threshold: jobs reachable by walking
and transit within the threshold (median travel time over a two-hour window, from the schedule),
own tract included, from the latest weekly routing.
#}
select
    origin_geoid as geoid,
    departure_window,
    departure_date,
    minutes_threshold,
    jobs_reachable,
    total_jobs_region,
    lodes_year,
    gtfs_md5
from {{ ref('stg_job_access') }}
