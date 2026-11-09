{{ config(materialized='view', meta={"allow_in_app": true}) }}

{#
Live: stop visits that arrived in the last 2 hours, for "how late are buses right now"
questions. fct_stop_visit is updated every 15 minutes, so the newest visit is usually 15–30
minutes old. On time is RTD's rule: less than 1 minute early to 5 minutes late. The two
filters prune to today's and yesterday's partitions (well under 1 MB a query). No
service_date_mst column, so the dashboard's date filter doesn't apply.
#}
select
    v.service_date,
    v.route_id,
    r.route_name,
    r.route_long_name,
    v.direction_id,
    v.trip_id,
    v.trip_headsign,
    v.stop_id,
    s.stop_name,
    s.lat,
    s.lon,
    v.stop_sequence,
    v.vehicle_id,
    v.skipped,
    v.arrival_ts_utc,
    datetime(v.arrival_ts_utc, 'America/Denver') as arrival_time_mst,
    v.delay_sec,
    round(v.delay_sec / 60, 1) as delay_min,
    case when v.delay_sec is null then null else v.delay_sec > -60 and v.delay_sec <= 300 end
        as is_on_time,
    timestamp_diff(current_timestamp(), v.arrival_ts_utc, minute) as minutes_ago,
    v.data_version
from {{ ref('fct_stop_visit') }} as v
left join {{ ref('dim_route') }} as r
    on v.route_id = r.route_id and r.is_latest_version
left join {{ ref('dim_stop') }} as s
    on v.stop_id = s.stop_id and s.is_latest_version
where v.service_date >= date_sub(current_date('America/Denver'), interval 1 day)
  and v.arrival_ts_utc >= timestamp_sub(current_timestamp(), interval 2 hour)
