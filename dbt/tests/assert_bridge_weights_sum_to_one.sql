-- Each stop's tract weights must sum to 1 so weighted averages stay on the indicator's scale.
select
    stop_key,
    sum(weighting_factor) as total_weight
from {{ ref('bridge_stop_tract') }}
group by stop_key
having abs(sum(weighting_factor) - 1) > 1e-9
