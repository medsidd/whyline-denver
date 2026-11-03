{#
Stop-to-stop segments that run along a Denver transit lane: at least half of the straight line
between the two stops lies within 15 m of the lane. One row per segment and lane (a street can
carry a business-access lane and a transit-only lane on the same blocks). Lane attributes are
from Denver's transit lanes layer; year_built is a year only.
#}
with lanes as (
    select
        trim(json_value(properties_json, '$.CORRIDOR')) as corridor,  -- one feature has a trailing space
        json_value(properties_json, '$.LANE_TYPE') as lane_type,
        safe_cast(json_value(properties_json, '$.YEAR_BUILT') as int64) as year_built,
        st_union_agg(geom) as geom
    from {{ ref('stg_arcgis_reference') }}
    where layer = 'denver_transit_lanes' and geom is not null
    group by 1, 2, 3
),
pairs as (
    select distinct from_stop_id, to_stop_id
    from {{ ref('fct_segment_traversal') }}
),
segments as (
    select
        p.from_stop_id,
        p.to_stop_id,
        st_makeline(a.geom, b.geom) as line
    from pairs as p
    join {{ ref('dim_stop') }} as a
        on a.stop_id = p.from_stop_id and a.is_current
    join {{ ref('dim_stop') }} as b
        on b.stop_id = p.to_stop_id and b.is_current
    where not st_equals(a.geom, b.geom)
),
overlap as (
    select
        s.from_stop_id,
        s.to_stop_id,
        l.corridor,
        l.lane_type,
        l.year_built,
        safe_divide(st_length(st_intersection(s.line, st_buffer(l.geom, 15))), st_length(s.line)) as share_on_lane
    from segments as s
    join lanes as l
        on st_dwithin(s.line, l.geom, 15)
)

select *
from overlap
where share_on_lane >= 0.5
