{# Grain: one month x NTD mode x type of service for RTD (NTD monthly module). #}
select
    month,
    mode,
    tos,
    mode_group,
    upt,
    vrm,
    vrh,
    voms
from {{ ref('stg_ntd_monthly') }}
