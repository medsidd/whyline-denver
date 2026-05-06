{{ config(materialized='view', meta={"allow_in_app": false}) }}
select
    stop_id, as_of_date, window_days,
    crash_100m_cnt, severe_100m_cnt, fatal_100m_cnt,
    crash_250m_cnt, severe_250m_cnt, fatal_250m_cnt, build_run_at
from {{ ref('mart_stop_safety') }}
