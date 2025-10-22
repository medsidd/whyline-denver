{{ config(materialized='table', meta={"allow_in_app": true}) }}

with buffers as (
    select
        stop_id,
        st_buffer(geom, 200) as buf
    from {{ ref('stg_gtfs_stops') }}
),
sidewalk_len as (
    select
        b.stop_id,
        sum(st_length(st_intersection(sw.geom, b.buf))) as tot_len_m
    from buffers as b
    join {{ ref('stg_sidewalks') }} as sw
        on st_intersects(sw.geom, b.buf)
    group by
        b.stop_id
),
stops as (
    select
        b.stop_id,
        200 as buffer_m,
        coalesce(s.tot_len_m, 0) as sidewalk_len_m_within_200m
    from buffers as b
    left join sidewalk_len as s
        using (stop_id)
)

select
    stop_id,
    buffer_m,
    sidewalk_len_m_within_200m,
    cast(
        round(
            case
                when max(sidewalk_len_m_within_200m) over () = min(sidewalk_len_m_within_200m) over ()
                    then 100
                else (
                    (sidewalk_len_m_within_200m - min(sidewalk_len_m_within_200m) over ()) /
                    nullif(
                        max(sidewalk_len_m_within_200m) over () - min(sidewalk_len_m_within_200m) over (),
                        0
                    ) * 100
                )
            end,
            1
        ) as float64
    ) as access_score_0_100,
    current_timestamp() as build_run_at
from stops
