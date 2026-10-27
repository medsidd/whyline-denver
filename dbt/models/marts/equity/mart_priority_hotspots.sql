{{ config(materialized='table', meta={"allow_in_app": true}) }}

with rel as (
    select
        stop_id,
        100.0 * (1 - avg(pct_on_time)) as reliability_score_0_100
    from {{ ref('mart_reliability_by_stop_hour') }}
    where service_date_mst >= date_sub(current_date("America/Denver"), interval 35 day)
    group by stop_id
),
cr as (
    select
        stop_id,
        cast(
            round(
                (crash_250m_cnt - min(crash_250m_cnt) over ()) /
                nullif(
                    max(crash_250m_cnt) over () - min(crash_250m_cnt) over (),
                    0
                ) * 100,
                1
            ) as float64
        ) as crash_score_0_100
    from {{ ref('mart_crash_proximity_by_stop') }}
),
v as (
    select
        stop_id,
        vuln_score_0_100
    from {{ ref('mart_vulnerability_by_stop') }}
),
joined as (
    select
        coalesce(v.stop_id, cr.stop_id, rel.stop_id) as stop_id,
        v.vuln_score_0_100,
        cr.crash_score_0_100,
        rel.reliability_score_0_100
    from v
    full outer join cr
        using (stop_id)
    full outer join rel
        using (stop_id)
),
scored as (
    select
        stop_id,
        vuln_score_0_100,
        crash_score_0_100,
        reliability_score_0_100,
        0.5 * coalesce(vuln_score_0_100, 0)
        + 0.3 * coalesce(crash_score_0_100, 0)
        + 0.2 * coalesce(reliability_score_0_100, 0) as priority_score
    from joined
)

select
    sc.stop_id,
    sc.vuln_score_0_100,
    sc.crash_score_0_100,
    sc.reliability_score_0_100,
    sc.priority_score,
    dense_rank() over (order by sc.priority_score desc) as priority_rank,
    current_timestamp() as build_run_at,
    s.stop_name,
    s.lat,
    s.lon
from scored as sc
left join {{ ref('dim_stop') }} as s
    on s.stop_id = sc.stop_id
    and s.is_latest_version
where sc.stop_id is not null
