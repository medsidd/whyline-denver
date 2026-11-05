{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
Did the bus lane help? Weekly running speed on each transit-lane corridor beside the same routes'
segments that have no lane, by period. Every Denver lane in the city's layer was built by 2022,
before WhyLine's timed data starts (2026-10-28), so a before-and-after needs a lane that opens
later: set its date in var('lane_openings', {'Corridor name': 'YYYY-MM-DD'}) and
weeks_since_opening fills in. Until then the comparison is cross-sectional: lane segments are on
downtown streets that differ from the comparison segments in more than the lane.
#}
{% set openings = var('lane_openings', {}) %}

with lane_segments as (
    select from_stop_id, to_stop_id, corridor, lane_type, year_built
    from {{ ref('bridge_segment_transit_lane') }}
),
traversals as (
    select
        t.*,
        date_trunc(t.service_date, week(monday)) as week_start,
        case
            when t.depart_hour_mst between 4 and 6 then 'early'
            when t.depart_hour_mst between 7 and 8 then 'am_peak'
            when t.depart_hour_mst between 9 and 14 then 'midday'
            when t.depart_hour_mst between 15 and 17 then 'pm_peak'
            when t.depart_hour_mst between 18 and 20 then 'evening'
            else 'night'
        end as period,
        safe_divide(t.travel_sec, nullif(t.scheduled_travel_sec, 0)) as delay_ratio
    from {{ ref('fct_segment_traversal') }} as t
),
on_lane as (
    select distinct l.corridor, t.route_id
    from traversals as t
    join lane_segments as l
        on l.from_stop_id = t.from_stop_id and l.to_stop_id = t.to_stop_id
),
grouped as (
    -- The corridor's own lane segments.
    select l.corridor, 'lane' as segment_group, t.week_start, t.period, t.speed_kmh, t.delay_ratio
    from traversals as t
    join (select distinct from_stop_id, to_stop_id, corridor from lane_segments) as l
        on l.from_stop_id = t.from_stop_id and l.to_stop_id = t.to_stop_id
    union all
    -- The same routes elsewhere, on segments with no lane at all.
    select r.corridor, 'same_routes_no_lane', t.week_start, t.period, t.speed_kmh, t.delay_ratio
    from traversals as t
    join on_lane as r
        on r.route_id = t.route_id
    where not exists (
        select 1 from lane_segments as l
        where l.from_stop_id = t.from_stop_id and l.to_stop_id = t.to_stop_id
    )
),
lane_years as (
    select corridor, min(year_built) as first_year_built, max(year_built) as last_year_built
    from lane_segments
    group by 1
)

select
    g.corridor,
    g.segment_group,
    g.week_start,
    g.period,
    count(*) as n_traversals,
    approx_quantiles(g.speed_kmh, 100)[offset(50)] as p50_speed_kmh,
    approx_quantiles(g.delay_ratio, 100)[offset(50)] as p50_delay_ratio,
    any_value(y.first_year_built) as first_year_built,
    any_value(y.last_year_built) as last_year_built,
    {% if openings %}
    case g.corridor
        {%- for corridor, opened in openings.items() %}
        when '{{ corridor }}' then date_diff(g.week_start, date '{{ opened }}', week(monday))
        {%- endfor %}
    end as weeks_since_opening,
    {% else %}
    cast(null as int64) as weeks_since_opening,
    {% endif %}
    current_timestamp() as build_run_at
from grouped as g
left join lane_years as y
    using (corridor)
group by 1, 2, 3, 4
