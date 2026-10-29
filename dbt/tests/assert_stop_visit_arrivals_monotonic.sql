{{ config(severity='warn') }}

-- Within a trip, a later stop should not be reached more than a minute before an earlier one.
-- Warn-level: a regression points at a projection or attribution problem, not a load failure.
with visits as (
    select
        service_date,
        trip_id,
        stop_sequence,
        arrival_ts_utc,
        lag(arrival_ts_utc) over (
            partition by service_date, trip_id order by stop_sequence
        ) as previous_arrival_ts
    from {{ ref('fct_stop_visit') }}
    where service_date >= date_sub(current_date('America/Denver'), interval 2 day)
      and arrival_ts_utc is not null
)

select *
from visits
where arrival_ts_utc < timestamp_sub(previous_arrival_ts, interval 60 second)
