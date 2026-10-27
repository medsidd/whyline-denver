-- An empty schedule for today means no usable GTFS snapshot in the nightly window; delays and
-- headways would silently lose their schedule baseline.
select current_date('America/Denver') as service_date_without_schedule
from (select 1)
where not exists (
    select 1
    from {{ ref('fct_scheduled_stop_time') }}
    where service_date_mst = current_date('America/Denver')
)
