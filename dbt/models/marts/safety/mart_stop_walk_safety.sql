{{ config(materialized='table', cluster_by=['stop_id'], meta={"allow_in_app": false}) }}

{#
Is it safe and accessible to walk to this stop? For each stop inside Denver, the street around
it (bridge_stop_street_safety) and plain-language flags: on the High Injury Network with no
traffic signal within 100 m, no curb ramp within 50 m, no sidewalk on a quarter or more of the
street frontage within 100 m. Pedestrian crash counts are in
mart_crash_proximity_by_stop. Published with release R2.
#}
select
    b.stop_id,
    st.stop_name,
    st.lat,
    st.lon,
    b.on_hin,
    b.hin_tier,
    b.nearest_signal_m,
    b.n_curb_ramps_50m,
    b.existing_bikeway_within_100m,
    b.on_transit_lane,
    b.transit_signal_priority_within_50m,
    b.queue_jump_within_50m,
    b.frontage_m_100m,
    b.pct_frontage_no_sidewalk_100m,
    b.pct_sidewalk_under_5ft_100m,
    b.pct_sidewalk_fair_or_poor_100m,
    array_to_string(
        array(
            select flag from unnest([
                if(b.on_hin and coalesce(b.nearest_signal_m, 1000) > 100, 'on the High Injury Network, no signal within 100 m', null),
                if(b.on_hin and b.hin_tier = 1, 'on a tier 1 High Injury Network street', null),
                if(b.n_curb_ramps_50m = 0, 'no curb ramp recorded within 50 m', null),
                if(b.pct_frontage_no_sidewalk_100m >= 0.25, 'no sidewalk on a quarter or more of the street frontage within 100 m', null)
            ]) as flag
            where flag is not null
        ),
        '; '
    ) as walk_safety_flags,
    current_timestamp() as build_run_at
from {{ ref('bridge_stop_street_safety') }} as b
left join {{ ref('dim_stop') }} as st
    on st.stop_id = b.stop_id
    and st.is_current
