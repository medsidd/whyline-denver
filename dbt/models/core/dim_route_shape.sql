{{ config(materialized='table') }}

{#
Each route's most-run shape per direction in the latest GTFS extract, as a GEOGRAPHY line.
Current schedule only (no history): it draws routes on maps. Both filters inline the latest
extract date, so each scan reads one partition (about 7 MB).
#}
with trips as (
    select
        route_id,
        coalesce(direction_id, 0) as direction_id,
        shape_id,
        count(*) as n_trips
    from {{ ref('stg_gtfs_trips') }}
    where _extract_date = {{ latest_extract_date(source('raw', 'raw_gtfs_trips')) }}
      and is_valid
      and shape_id is not null
    group by 1, 2, 3
),

ranked as (
    select
        *,
        row_number() over (
            partition by route_id, direction_id order by n_trips desc, shape_id
        ) as rn
    from trips
),

shapes as (
    select shape_id, geom
    from {{ ref('stg_gtfs_shapes') }}
    where _extract_date = {{ latest_extract_date(source('raw', 'raw_gtfs_shapes')) }}
      and is_valid
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
