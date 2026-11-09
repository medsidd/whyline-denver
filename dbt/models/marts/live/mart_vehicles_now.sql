{{ config(materialized='view', meta={"allow_in_app": true}) }}

{#
Live: vehicles running in the newest load, one row each, for "right now" questions. A vehicle
counts when its latest report is within 10 minutes of the newest report in the last 45
minutes of feed time, so a bus that stopped reporting drops out with the next load instead of
lingering. A view, so every query reads the newest load; the feed_ts_utc filter prunes to
today's raw partition (about 2.6 MB a query). Loads arrive every 15 minutes, so minutes_ago is
usually 15–30. No service_date_mst column, so the dashboard's date filter doesn't apply.
#}
with recent as (
    select *
    from {{ ref('fct_vehicle_report') }}
    where feed_ts_utc >= timestamp_sub(current_timestamp(), interval 45 minute)
      and vehicle_id is not null
),

latest as (
    select *
    from recent
    qualify row_number() over (partition by vehicle_id order by report_ts_utc desc) = 1
),

current_vehicles as (
    select *
    from latest
    qualify report_ts_utc >= timestamp_sub(max(report_ts_utc) over (), interval 10 minute)
)

select
    l.vehicle_id,
    l.vehicle_label,
    l.route_id,
    r.route_name,
    r.route_long_name,
    r.route_type,
    l.direction_id,
    l.trip_id,
    l.stop_id,
    s.stop_name,
    l.current_status,
    l.lat,
    l.lon,
    l.bearing,
    round(l.speed_mps * 3.6, 1) as speed_kmh,
    l.occupancy_status,
    l.report_ts_utc,
    {{ as_mst('l.report_ts_utc') }} as report_ts_mst,
    timestamp_diff(current_timestamp(), l.report_ts_utc, minute) as minutes_ago
from current_vehicles as l
left join {{ ref('dim_route') }} as r
    on l.route_id = r.route_id and r.is_latest_version
left join {{ ref('dim_stop') }} as s
    on l.stop_id = s.stop_id and s.is_latest_version
