{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['trip_id', 'stop_id']
    )
}}

{#
Grain: one scheduled stop per trip x stop_sequence x service date.
Each date is expanded from the GTFS snapshot that was current on it (as-of join), so the
past keeps the schedule as published.
- A day's load is a usable snapshot only if every file loaded that day passed validation:
  the positional CSV load shifted columns on some days (2025-12-09 to 2026-01-04), and
  mixing that day's valid files with an older feed would pair mismatched trip ids.
- Each date uses the latest snapshot on or before it; if that snapshot's calendar has no
  service on the date (a new period first captured a day late), the next snapshot is used.
- The loader skips files whose content did not change, so each file then uses its latest
  valid extract on or before the chosen snapshot.
- Nightly incremental runs replace today through +lookahead, reading each file's most
  recent extract partitions (constant filter, so BigQuery prunes); a full refresh
  rebuilds from schedule_history_start.
#}
{% set lookahead_days = var('schedule_lookahead_days', 30) %}
{% set files = {
    'calendar': 'raw_gtfs_calendar',
    'calendar_dates': 'raw_gtfs_calendar_dates',
    'trips': 'raw_gtfs_trips',
    'stop_times': 'raw_gtfs_stop_times',
} %}
{% set extract_filter = {} %}
{% for name, table in files.items() %}
    {% if is_incremental() %}
        {% do extract_filter.update({name: recent_extracts_filter(source('raw', table), var('schedule_recent_extracts', 7))}) %}
    {% else %}
        {% do extract_filter.update({name: 'true'}) %}
    {% endif %}
{% endfor %}
{% if is_incremental() %}
    {% set start_date = "current_date('America/Denver')" %}
{% else %}
    {% set start_date = "date '" ~ var('schedule_history_start', '2025-10-23') ~ "'" %}
{% endif %}

with calendar as (
    select * from {{ ref('stg_gtfs_calendar') }} where {{ extract_filter['calendar'] }}
),
calendar_dates as (
    select * from {{ ref('stg_gtfs_calendar_dates') }} where {{ extract_filter['calendar_dates'] }}
),
trips as (
    select _extract_date, trip_id, route_id, direction_id, service_id, is_valid
    from {{ ref('stg_gtfs_trips') }}
    where {{ extract_filter['trips'] }}
),
stop_times as (
    select _extract_date, trip_id, stop_id, stop_sequence, arrival_time, departure_time, is_valid
    from {{ ref('stg_gtfs_stop_times') }}
    where {{ extract_filter['stop_times'] }}
),
file_extracts as (
    {%- for name in files %}
    select
        '{{ name }}' as gtfs_file,
        _extract_date,
        logical_and(is_valid) as all_valid,
        logical_or(is_valid) as any_valid
    from {{ name }}
    group by _extract_date
    {%- if not loop.last %}
    union all{% endif %}
    {%- endfor %}
),
good_snapshots as (
    select _extract_date
    from file_extracts
    group by _extract_date
    having logical_and(all_valid)
),
date_candidates as (
    select
        service_date,
        max(if(g._extract_date <= service_date, g._extract_date, null)) as prev_snapshot,
        min(if(g._extract_date > service_date, g._extract_date, null)) as next_snapshot
    from unnest(generate_date_array(
        {{ start_date }},
        date_add(current_date('America/Denver'), interval {{ lookahead_days }} day)
    )) as service_date
    cross join good_snapshots as g
    group by service_date
),
date_snapshot as (
    -- Preference 1: latest snapshot on or before the date; 2: the next one
    select
        dc.service_date,
        candidate.snapshot_date,
        candidate.preference
    from date_candidates as dc
    cross join unnest([
        struct(dc.prev_snapshot as snapshot_date, 1 as preference),
        struct(dc.next_snapshot as snapshot_date, 2 as preference)
    ]) as candidate
    where candidate.snapshot_date is not null
),
date_extract as (
    -- Per file: latest valid extract on or before the snapshot (unchanged files are not reloaded)
    select
        ds.service_date,
        ds.preference
        {%- for name in files %},
        coalesce(
            max(if(fe.gtfs_file = '{{ name }}' and fe.any_valid and fe._extract_date <= ds.snapshot_date, fe._extract_date, null)),
            min(if(fe.gtfs_file = '{{ name }}' and fe.any_valid, fe._extract_date, null))
        ) as {{ name }}_extract
        {%- endfor %}
    from date_snapshot as ds
    cross join file_extracts as fe
    group by ds.service_date, ds.preference
),
active_services as (
    select
        de.service_date,
        de.preference,
        de.trips_extract,
        de.stop_times_extract,
        c.service_id
    from date_extract as de
    join calendar as c
        on c._extract_date = de.calendar_extract
        and c.is_valid
        and de.service_date between c.start_date and c.end_date
        and case extract(dayofweek from de.service_date)
            when 1 then c.sunday
            when 2 then c.monday
            when 3 then c.tuesday
            when 4 then c.wednesday
            when 5 then c.thursday
            when 6 then c.friday
            when 7 then c.saturday
        end
    left join calendar_dates as removed
        on removed._extract_date = de.calendar_dates_extract
        and removed.service_id = c.service_id
        and removed.exception_date = de.service_date
        and removed.exception_type = 2
        and removed.is_valid
    where removed.service_id is null

    union distinct

    select
        de.service_date,
        de.preference,
        de.trips_extract,
        de.stop_times_extract,
        cd.service_id
    from date_extract as de
    join calendar_dates as cd
        on cd._extract_date = de.calendar_dates_extract
        and cd.exception_date = de.service_date
        and cd.exception_type = 1
        and cd.is_valid
),
chosen_services as (
    -- Use the next snapshot only when the preferred one runs no service that day
    select *
    from active_services
    qualify preference = min(preference) over (partition by service_date)
),
expanded as (
    select
        a.service_date,
        a.stop_times_extract,
        t.trip_id,
        t.route_id,
        t.direction_id,
        st.stop_id,
        st.stop_sequence,
        case
            when st.arrival_time is not null
                then {{ gtfs_time_to_ts('a.service_date', 'st.arrival_time') }}
        end as sched_arrival_ts_mst,
        case
            when st.departure_time is not null
                then {{ gtfs_time_to_ts('a.service_date', 'st.departure_time') }}
        end as sched_departure_ts_mst
    from chosen_services as a
    join trips as t
        on t._extract_date = a.trips_extract
        and t.service_id = a.service_id
        and t.is_valid
    join stop_times as st
        on st._extract_date = a.stop_times_extract
        and st.trip_id = t.trip_id
        and st.is_valid
)

select
    e.service_date as service_date_mst,
    e.trip_id,
    e.stop_id,
    e.stop_sequence,
    e.route_id,
    e.direction_id,
    coalesce(dt.trip_key, -1) as trip_key,
    coalesce(dr.route_key, -1) as route_key,
    coalesce(ds.stop_key, -1) as stop_key,
    e.sched_arrival_ts_mst,
    e.sched_departure_ts_mst,
    e.stop_times_extract as gtfs_extract_date
from expanded as e
left join {{ ref('dim_trip') }} as dt
    on dt.trip_id = e.trip_id
    and e.service_date between dt.valid_from and dt.valid_to
left join {{ ref('dim_route') }} as dr
    on dr.route_id = e.route_id
    and e.service_date between dr.valid_from and dr.valid_to
left join {{ ref('dim_stop') }} as ds
    on ds.stop_id = e.stop_id
    and e.service_date between ds.valid_from and ds.valid_to
where e.sched_arrival_ts_mst is not null or e.sched_departure_ts_mst is not null
