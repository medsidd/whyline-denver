{{ config(materialized='view', meta={"allow_in_app": false}) }}
select
    stop_id, vuln_score_0_100, crash_score_0_100,
    reliability_score_0_100, priority_score, priority_rank, build_run_at
from {{ ref('mart_stop_priority') }}
