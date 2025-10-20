{{ config(materialized='view') }}

select
    {{ date_mst('feed_ts_utc') }} as feed_date_mst,
    count(*) as event_rows,
    count(distinct trip_id) as trips_observed,
    count(distinct route_id) as routes_observed,
    min(feed_ts_utc) as first_feed_ts_utc,
    max(feed_ts_utc) as last_feed_ts_utc
from {{ ref('stg_rt_events') }}
group by 1
