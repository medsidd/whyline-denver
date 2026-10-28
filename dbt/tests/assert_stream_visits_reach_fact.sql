-- Raw stream partitions expire after 90 days and fct_stop_visit is the permanent copy, so every
-- stream visit must reach the fact long before then. Checks the rows loaded in a two-hour slice
-- two days ago (raw is partitioned by load hour, so this stays a few MB).
select r.service_date, r.trip_id, r.stop_sequence, r._ingested_at
from {{ ref('stg_rt_stop_visits') }} as r
left join {{ ref('fct_stop_visit') }} as f
    on f.service_date = r.service_date
    and f.trip_id = r.trip_id
    and f.stop_sequence = r.stop_sequence
    and f.service_date >= date_sub(current_date('America/Denver'), interval 7 day)
where r._ingested_at >= timestamp_sub(current_timestamp(), interval 50 hour)
  and r._ingested_at < timestamp_sub(current_timestamp(), interval 48 hour)
  and r.data_version = 'stream_v1'
  and r.service_date >= date_sub(current_date('America/Denver'), interval 7 day)
  and f.trip_id is null
