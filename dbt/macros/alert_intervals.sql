{% macro alert_intervals() %}
{#
Each alert's informed entities with the interval they were affected, from the alert's last
snapshot (so RTD's later edits win). Start: the period start, else when the alert was first seen.
End: the period end; once the alert has left the feed (last seen over 30 minutes before the
newest snapshot), no later than 15 minutes after it was last seen. NULL end means still open.
#}
    select
        p.alert_id,
        p.route_id,
        p.direction_id,
        p.stop_id,
        p.trip_id,
        a.cause,
        a.effect,
        a.header_text,
        a.last_seen_ts < timestamp_sub(n.newest_ts, interval 30 minute) as has_ended,
        coalesce(p.active_start_utc, a.first_seen_ts) as start_ts,
        case
            when a.last_seen_ts < timestamp_sub(n.newest_ts, interval 30 minute)
                then least(
                    coalesce(p.active_end_utc, timestamp_add(a.last_seen_ts, interval 15 minute)),
                    timestamp_add(a.last_seen_ts, interval 15 minute)
                )
            else p.active_end_utc
        end as end_ts
    from {{ ref('fct_alert_entity_period') }} as p
    join {{ ref('fct_alert') }} as a
        on a.alert_id = p.alert_id
        and p.last_seen_ts = a.last_seen_ts
    cross join (select max(last_seen_ts) as newest_ts from {{ ref('fct_alert') }}) as n
{% endmacro %}
