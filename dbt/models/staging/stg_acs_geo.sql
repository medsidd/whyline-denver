{{ config(materialized='view') }}

with base as (
    select
        geoid,
        name,
        year,
        hh_no_vehicle,
        hh_total,
        workers_transit,
        workers_total,
        persons_poverty,
        pop_total,
        pct_hh_no_vehicle,
        pct_transit_commute,
        pct_poverty,
        _ingested_at
    from {{ source('raw', 'raw_acs_tract') }}
),
deduped as (
    select
        *,
        row_number() over (
            partition by geoid
            order by year desc, _ingested_at desc
        ) as tract_rank
    from base
)

select
    geoid,
    name,
    year,
    hh_no_vehicle,
    hh_total,
    workers_transit,
    workers_total,
    persons_poverty,
    pop_total,
    pct_hh_no_vehicle,
    pct_transit_commute,
    pct_poverty
from deduped
where tract_rank = 1
