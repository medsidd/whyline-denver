{#
Type 1: Denver census block groups (2020) with the state's and city's equity measures.
- Colorado EnviroScreen 2.0 (CDPHE): the EnviroScreen percentile within Colorado, and the
  disproportionately impacted community type under Colorado law (N/A when not impacted).
- Denver DOTI equity index: the score (16-68 in 2026; higher means more need) and group rank
  (1 is the highest-need group, 6 the lowest).
#}
with enviroscreen as (
    select
        json_value(properties_json, '$.GEOID') as geoid,
        safe_cast(json_value(properties_json, '$.ES_S_') as float64) as enviroscreen_pctl,
        nullif(json_value(properties_json, '$.DIType'), 'N/A') as di_community_type,
        geom
    from {{ ref('stg_arcgis_reference') }}
    where layer = 'enviroscreen_block_group'
    qualify row_number() over (partition by geoid order by object_id) = 1
),
doti as (
    -- One block group (080319800011, the airport) comes in two parts; merge them.
    select
        json_value(properties_json, '$.GEOID20') as geoid,
        max(safe_cast(json_value(properties_json, '$.EquityScore') as int64)) as doti_equity_score,
        min(safe_cast(json_value(properties_json, '$.EquityGroupRank') as int64)) as doti_equity_group_rank,
        st_union_agg(geom) as geom
    from {{ ref('stg_arcgis_reference') }}
    where layer = 'denver_doti_equity'
    group by 1
)

select
    farm_fingerprint(coalesce(e.geoid, d.geoid)) as block_group_key,
    coalesce(e.geoid, d.geoid) as geoid,
    substr(coalesce(e.geoid, d.geoid), 1, 11) as tract_geoid,
    e.enviroscreen_pctl,
    e.di_community_type,
    e.di_community_type is not null as is_disproportionately_impacted,
    d.doti_equity_score,
    d.doti_equity_group_rank,
    coalesce(e.geom, d.geom) as geom
from enviroscreen as e
full join doti as d
    on d.geoid = e.geoid
where coalesce(e.geoid, d.geoid) is not null
union all
select
    -1, cast(null as string), cast(null as string), cast(null as float64), cast(null as string), false,
    cast(null as int64), cast(null as int64), cast(null as geography)
