{# Current stop x the Denver block group containing it; stops outside Denver have no row. #}
select
    s.stop_id,
    b.geoid,
    b.block_group_key
from {{ ref('dim_stop') }} as s
join {{ ref('dim_block_group') }} as b
    on st_contains(b.geom, s.geom)
where s.is_current
qualify row_number() over (partition by s.stop_id order by b.geoid) = 1
