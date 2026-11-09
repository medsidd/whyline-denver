{#
Each route's most-run shape per direction in the latest GTFS extract, as a GEOGRAPHY line.
Current schedule only (no history): it draws routes on maps. Both filters inline the latest
extract date, so each scan reads one partition (about 7 MB). Only valid shapes compete, so a
route keeps a line when its busiest shape is malformed. Limit: the count spans every service
period in the extract, so while a feed carries an upcoming runboard, its shape can win.
#}
with shapes as (
    select shape_id, geom
    from {{ ref('stg_gtfs_shapes') }}
    where _extract_date = {{ latest_extract_date(source('raw', 'raw_gtfs_shapes')) }}
      and is_valid
),

trips as (
    select
        t.route_id,
        coalesce(t.direction_id, 0) as direction_id,
        t.shape_id,
        count(*) as n_trips
    from {{ ref('stg_gtfs_trips') }} as t
    inner join shapes as s using (shape_id)
    where t._extract_date = {{ latest_extract_date(source('raw', 'raw_gtfs_trips')) }}
      and t.is_valid
    group by 1, 2, 3
),

ranked as (
    select
        *,
        row_number() over (
            partition by route_id, direction_id order by n_trips desc, shape_id
        ) as rn
    from trips
)

select
    r.route_id,
    r.direction_id,
    r.shape_id,
    r.n_trips,
    s.geom
from ranked as r
inner join shapes as s using (shape_id)
where r.rn = 1
