{{ config(materialized='view') }}

{#
Every GTFS extract, one line per shape. Filter on `_extract_date` with a constant; it is a
grouping key, so the filter pushes down. is_valid: at least two in-range points (a shifted
positional CSV load produces out-of-range coordinates, which SAFE turns into dropped points).
shape_dist_traveled is metres in current feeds and empty in some 2025 feeds.
#}
with points as (
    select
        _extract_date,
        shape_id,
        shape_pt_sequence,
        shape_dist_traveled,
        safe.st_geogpoint(shape_pt_lon, shape_pt_lat) as point
    from {{ source('raw', 'raw_gtfs_shapes') }}
),
lines as (
    select
        _extract_date,
        shape_id,
        st_makeline(array_agg(point ignore nulls order by shape_pt_sequence)) as geom,
        count(*) as n_points,
        countif(point is null) as n_bad_points,
        max(shape_dist_traveled) as max_dist_m
    from points
    group by _extract_date, shape_id
)
select
    _extract_date,
    shape_id,
    geom,
    st_length(geom) as length_m,
    max_dist_m,
    n_points,
    n_bad_points = 0 and n_points >= 2 as is_valid
from lines
