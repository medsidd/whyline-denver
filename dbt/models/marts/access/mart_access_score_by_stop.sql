{{ config(materialized='view', meta={"allow_in_app": false}) }}
select stop_id, buffer_m, sidewalk_len_m_within_200m, access_score_0_100, build_run_at
from {{ ref('mart_stop_access') }}
