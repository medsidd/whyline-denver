{{ config(materialized='table', cluster_by=['stop_id'], meta={"allow_in_app": false}) }}

{#
Stops named in RTD service alerts, current and past: one row per stop and alert, with when the
alert applied and whether it is in effect now. is_closure marks NO_SERVICE and STOP_MOVED alerts;
detours often close stops too but say so only in the text. History starts when snapshots began
(2026-11-02); earlier alerts are missing unless still in the feed then.
#}
with intervals as (
    {{ alert_intervals() }}
)

select
    i.stop_id,
    any_value(st.stop_name) as stop_name,
    any_value(st.lat) as lat,
    any_value(st.lon) as lon,
    i.alert_id,
    any_value(i.cause) as cause,
    any_value(i.effect) as effect,
    any_value(i.effect) in ('NO_SERVICE', 'STOP_MOVED') as is_closure,
    any_value(i.header_text) as header_text,
    string_agg(distinct i.route_id, ',' order by i.route_id) as route_ids,
    min(i.start_ts) as from_ts,
    if(countif(i.end_ts is null) > 0, null, max(i.end_ts)) as until_ts,
    logical_and(not i.has_ended)
    and min(i.start_ts) <= current_timestamp()
    and (countif(i.end_ts is null) > 0 or max(i.end_ts) > current_timestamp()) as is_active_now,
    current_timestamp() as build_run_at
from intervals as i
left join {{ ref('dim_stop') }} as st
    on st.stop_id = i.stop_id
    and st.is_current
where i.stop_id is not null
group by i.stop_id, i.alert_id
