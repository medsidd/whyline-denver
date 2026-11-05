{{ config(materialized='view') }}

{# Silver: jobs reachable by transit per tract, window and threshold, from the latest weekly extract. #}
select
    origin_geoid,
    `window` as departure_window,  -- WINDOW is reserved in BigQuery
    departure_date,
    minutes_threshold,
    jobs_reachable,
    total_jobs_region,
    lodes_year,
    gtfs_md5
from {{ source('raw', 'raw_job_access') }}
where _extract_date = {{ latest_extract_date(source('raw', 'raw_job_access')) }}
qualify row_number() over (partition by origin_geoid, `window`, minutes_threshold order by _ingested_at desc) = 1
