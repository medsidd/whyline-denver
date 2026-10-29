-- Calibration of backfill_v1 against stream_v1, run after 2-4 weeks of stream data (owner-run):
-- 1. Replay the archive thinned to one refresh per 15 minutes, without vehicle stop fields, in backfill mode:
--    make replay-gtfs-rt REPLAY_SOURCE=gs://whylinedenver-rt-archive FROM=<d1> UNTIL=<d2> REPLAY_OUT=data/calibration \
--      REPLAY_FLAGS="--thin-minutes 15 --strip-vp-stop-fields --engine-mode backfill --window-minutes 1440"
-- 2. gcloud storage cp -r data/calibration/snapshot_at=* gs://whylinedenver-raw/raw/rtd_gtfsrt_calibration/
-- 3. python -m whyline.load.bq_load --src gcs --bucket whylinedenver-raw --from <d1> --until <d2>
-- 4. dbt compile --select backfill_calibration --vars '{calibration_from: "<d1>", calibration_until: "<d2>"}'
--    and run the compiled SQL. Record the results in docs/public/METRICS_GLOSSARY.md before publishing
--    backfilled metrics.
-- Ground truth: stream shape_crossing visits (bracketing reports at most 30 s apart).
-- error_sec = backfill-method estimate minus stream estimate (positive: the backfill runs late).
{% set d1 = var('calibration_from', '2100-01-01') %}
{% set d2 = var('calibration_until', '2100-01-01') %}

with stream as (
    select service_date, trip_id, stop_sequence, route_id, arrival_ts_utc, arrival_hour_mst
    from {{ ref('fct_stop_visit') }}
    where service_date between date '{{ d1 }}' and date '{{ d2 }}'
      and data_version = 'stream_v1'
      and arrival_method = 'shape_crossing'
),
thinned as (
    select service_date, trip_id, stop_sequence, arrival_ts_utc, arrival_method, low_confidence,
        timestamp_diff(arrival_latest_ts, arrival_earliest_ts, second) as window_sec
    from {{ source('raw', 'raw_gtfsrt_stop_visits_calibration') }}
    where service_date between date '{{ d1 }}' and date '{{ d2 }}'
      and arrival_ts_utc is not null
    qualify row_number() over (
        partition by service_date, trip_id, stop_sequence order by _ingested_at desc
    ) = 1
),
paired as (
    select
        s.*,
        coalesce(t.arrival_method, 'not_recovered') as backfill_method,
        t.low_confidence,
        t.window_sec,
        timestamp_diff(t.arrival_ts_utc, s.arrival_ts_utc, second) as error_sec
    from stream as s
    left join thinned as t using (service_date, trip_id, stop_sequence)
)

select
    coalesce(backfill_method, 'all') as backfill_method,
    count(*) as n_stream_visits,
    round(count(*) / (select count(*) from stream), 4) as share_of_stream_visits,
    approx_quantiles(abs(error_sec), 100)[offset(50)] as median_abs_error_sec,
    approx_quantiles(abs(error_sec), 100)[offset(90)] as p90_abs_error_sec,
    round(avg(error_sec), 1) as bias_sec,
    approx_quantiles(window_sec, 100)[offset(50)] as median_window_sec,
    countif(low_confidence) as n_low_confidence
from paired
group by rollup (backfill_method)
order by n_stream_visits desc
