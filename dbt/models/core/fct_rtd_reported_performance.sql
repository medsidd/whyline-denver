{# Grain: one month x RTD service category x metric, as RTD printed it in its operations reports. #}
select
    report_month,
    mode,
    service,
    metric,
    value_pct,
    source_url
from {{ ref('stg_rtd_reported_performance') }}
