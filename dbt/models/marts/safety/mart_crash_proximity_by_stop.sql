{{ config(materialized='table', meta={"allow_in_app": true}) }}

with params as (
    select
        max(date(event_ts_utc)) as as_of_date,
        365 as window_days
    from {{ ref('stg_denver_crashes') }}
),
st as (
    select
        stop_id,
        geom
    from {{ ref('stg_gtfs_stops') }}
),
cr as (
    select
        event_ts_utc,
        geom,
        severity
    from {{ ref('stg_denver_crashes') }}
    cross join params
    where date(event_ts_utc) between date_sub(params.as_of_date, interval params.window_days day) and params.as_of_date
),
stop_crash as (
    select
        s.stop_id,
        params.as_of_date,
        params.window_days,
        cr.severity,
        st_distance(s.geom, cr.geom) as distance_m
    from params
    cross join st as s
    join cr
        on st_dwithin(s.geom, cr.geom, 250)
),
agg as (
    select
        stop_id,
        as_of_date,
        window_days,
        countif(distance_m <= 100) as crash_100m_cnt,
        countif(distance_m <= 100 and severity >= 3) as severe_100m_cnt,
        countif(distance_m <= 100 and severity = 4) as fatal_100m_cnt,
        count(*) as crash_250m_cnt,
        countif(severity >= 3) as severe_250m_cnt,
        countif(severity = 4) as fatal_250m_cnt
    from stop_crash
    group by
        stop_id,
        as_of_date,
        window_days
)

select
    s.stop_id,
    params.as_of_date as as_of_date,
    params.window_days as window_days,
    coalesce(a.crash_100m_cnt, 0) as crash_100m_cnt,
    coalesce(a.severe_100m_cnt, 0) as severe_100m_cnt,
    coalesce(a.fatal_100m_cnt, 0) as fatal_100m_cnt,
    coalesce(a.crash_250m_cnt, 0) as crash_250m_cnt,
    coalesce(a.severe_250m_cnt, 0) as severe_250m_cnt,
    coalesce(a.fatal_250m_cnt, 0) as fatal_250m_cnt,
    current_timestamp() as build_run_at
from st as s
cross join params
left join agg as a
    on s.stop_id = a.stop_id
    and params.as_of_date = a.as_of_date
    and params.window_days = a.window_days
