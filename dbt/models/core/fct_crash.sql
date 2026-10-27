{# Grain: one reported crash #}
select
    crash_id,
    event_date_mst as crash_date_mst,
    event_hour_mst as crash_hour_mst,
    event_ts_utc,
    severity,
    severity_text,
    roadway_name,
    on_route,
    off_route,
    bike_involved,
    ped_involved,
    geom
from {{ ref('stg_denver_crashes') }}
