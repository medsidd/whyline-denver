{{ config(
    materialized='table',
    meta={"allow_in_app": true, "layer": "mart"}
) }}

with rel as (
    select stop_id, reliability_score_0_100
    from {{ ref('mart_stop_reliability_score') }}
),

cr as (
    select stop_id, crash_score_0_100
    from {{ ref('mart_stop_safety') }}
),

v as (
    select stop_id, vuln_score_0_100
    from {{ ref('mart_stop_equity') }}
),

joined as (
    select
        coalesce(v.stop_id, cr.stop_id, rel.stop_id) as stop_id,
        v.vuln_score_0_100,
        cr.crash_score_0_100,
        rel.reliability_score_0_100
    from v
    full outer join cr  using (stop_id)
    full outer join rel using (stop_id)
),

scored as (
    select
        stop_id,
        vuln_score_0_100,
        crash_score_0_100,
        reliability_score_0_100,
          {{ var('priority_weight_equity',      0.5) }} * coalesce(vuln_score_0_100,         0)
        + {{ var('priority_weight_safety',      0.3) }} * coalesce(crash_score_0_100,        0)
        + {{ var('priority_weight_reliability', 0.2) }} * coalesce(reliability_score_0_100, 0)
            as priority_score
    from joined
)

select
    stop_id,
    vuln_score_0_100,
    crash_score_0_100,
    reliability_score_0_100,
    priority_score,
    dense_rank() over (order by priority_score desc) as priority_rank,
    current_timestamp() as build_run_at
from scored
where stop_id is not null
