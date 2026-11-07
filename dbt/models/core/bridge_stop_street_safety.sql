{#
One row per current stop inside Denver with the street around it, from Denver's open-data layers
(weekly): the High Injury Network within 30 m (tier 1 has the highest crash rates), the nearest
traffic signal (NULL beyond 1 km), curb ramps within 50 m, an existing bikeway within 100 m, a
transit lane within 20 m, transit signal priority or a queue jump within 50 m, and the sidewalk
along the street frontage within 100 m (Denver's sidewalk asset inventory). Stops outside
Denver have no row: the layers cover only the city, so absence there isn't evidence.
#}
with layers as (
    select layer, properties_json, geom
    from {{ ref('stg_arcgis_reference') }}
    where geom is not null
),
denver as (
    select st_union_agg(geom) as geom
    from {{ ref('dim_tract') }}
    where geom is not null
),
stops as (
    select s.stop_id, s.geom
    from {{ ref('dim_stop') }} as s
    cross join denver as d
    where s.is_current and st_contains(d.geom, s.geom)
),
hin as (
    select s.stop_id, min(safe_cast(json_value(l.properties_json, '$.Tier') as int64)) as hin_tier
    from stops as s
    join layers as l
        on l.layer = 'denver_hin'
        and st_dwithin(s.geom, l.geom, 30)
    group by 1
),
signals as (
    select s.stop_id, min(st_distance(s.geom, l.geom)) as nearest_signal_m
    from stops as s
    join layers as l
        on l.layer = 'denver_traffic_signals'
        and st_dwithin(s.geom, l.geom, 1000)
    group by 1
),
ramps as (
    select s.stop_id, count(*) as n_curb_ramps_50m
    from stops as s
    join layers as l
        on l.layer = 'denver_curb_ramps'
        and st_dwithin(s.geom, l.geom, 50)
    group by 1
),
bikeways as (
    select distinct s.stop_id
    from stops as s
    join layers as l
        on l.layer = 'denver_bike_facilities'
        and starts_with(json_value(l.properties_json, '$.DISPLAY_STATUS'), 'Existing')
        and st_dwithin(s.geom, l.geom, 100)
),
lanes as (
    select distinct s.stop_id
    from stops as s
    join layers as l
        on l.layer = 'denver_transit_lanes'
        and st_dwithin(s.geom, l.geom, 20)
),
transit_signals as (
    select
        s.stop_id,
        logical_or(json_value(l.properties_json, '$.TSP') = 'Yes') as has_tsp,
        logical_or(json_value(l.properties_json, '$.QUEUE_JUMP') = 'Yes') as has_queue_jump
    from stops as s
    join layers as l
        on l.layer = 'denver_transit_signals'
        and st_dwithin(s.geom, l.geom, 50)
    group by 1
),
sidewalks as (
    -- Frontage length inside the 100 m circle; "Missing Sidewalk" frontage has no sidewalk.
    select
        stop_id,
        sum(len_m) as frontage_m,
        sum(if(is_missing, len_m, 0)) as missing_m,
        sum(if(not is_missing, len_m, 0)) as sidewalk_m,
        sum(if(not is_missing and width_ft < 5, len_m, 0)) as under_5ft_m,
        sum(if(not is_missing and condition in ('Fair', 'Poor'), len_m, 0)) as fair_or_poor_m
    from (
        select
            s.stop_id,
            json_value(l.properties_json, '$.SIDEWALK_TYPE') = 'Missing Sidewalk' as is_missing,
            safe_cast(json_value(l.properties_json, '$.SIDEWALK_WIDTH') as float64) as width_ft,
            json_value(l.properties_json, '$.BASELINE_CONDITION') as condition,
            st_length(st_intersection(l.geom, s.buf)) as len_m
        from (select stop_id, geom, st_buffer(geom, 100) as buf from stops) as s
        join layers as l
            on l.layer = 'denver_sidewalk_assets'
            and st_dwithin(s.geom, l.geom, 100)
    )
    group by 1
)

select
    s.stop_id,
    h.hin_tier is not null as on_hin,
    h.hin_tier,
    round(g.nearest_signal_m, 1) as nearest_signal_m,
    coalesce(r.n_curb_ramps_50m, 0) as n_curb_ramps_50m,
    b.stop_id is not null as existing_bikeway_within_100m,
    l.stop_id is not null as on_transit_lane,
    coalesce(t.has_tsp, false) as transit_signal_priority_within_50m,
    coalesce(t.has_queue_jump, false) as queue_jump_within_50m,
    round(coalesce(w.frontage_m, 0), 1) as frontage_m_100m,
    round(safe_divide(w.missing_m, w.frontage_m), 4) as pct_frontage_no_sidewalk_100m,
    round(safe_divide(w.under_5ft_m, w.sidewalk_m), 4) as pct_sidewalk_under_5ft_100m,
    round(safe_divide(w.fair_or_poor_m, w.sidewalk_m), 4) as pct_sidewalk_fair_or_poor_100m
from stops as s
left join hin as h using (stop_id)
left join signals as g using (stop_id)
left join ramps as r using (stop_id)
left join bikeways as b using (stop_id)
left join lanes as l using (stop_id)
left join transit_signals as t using (stop_id)
left join sidewalks as w using (stop_id)
