{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'date_mst', 'data_type': 'date'},
    cluster_by=['stop_id'],
    on_schema_change='append_new_columns',
    full_refresh=false
) }}

{#
Veo scooters and bikes available near each stop in Denver: per local date, stop, hour and form
factor, the average number of available vehicles within 200 m over that hour's snapshots, and
how often there were none. Stops outside the City and County of Denver (Veo's service area) are
left out. Raw snapshots expire after 30 days, so this is kept permanently and full refresh is
disabled; nightly runs replace the last micromobility_days complete local dates.
#}
{% set days = var('micromobility_days', 2) %}
{% if is_incremental() %}
    {% set first = "date_sub(current_date('America/Denver'), interval " ~ days ~ " day)" %}
{% else %}
    {% set first = "date '" ~ var('micromobility_start', '2026-11-02') ~ "'" %}
{% endif %}
{% set last = "date_sub(current_date('America/Denver'), interval 1 day)" %}

with snapshots as (
    select distinct snapshot_ts_utc
    from {{ ref('stg_gbfs_veo_vehicles') }}
    where
        -- Constant bounds so BigQuery prunes the raw partitions; local days end after UTC midnight.
        snapshot_ts_utc >= timestamp({{ first }})
        and snapshot_ts_utc < timestamp(date_add({{ last }}, interval 2 day))
        and {{ date_mst('snapshot_ts_utc') }} between {{ first }} and {{ last }}
),
vehicles as (
    select v.snapshot_ts_utc, v.form_factor, v.geom
    from {{ ref('stg_gbfs_veo_vehicles') }} as v
    join snapshots as s
        on s.snapshot_ts_utc = v.snapshot_ts_utc
    where
        v.snapshot_ts_utc >= timestamp({{ first }})
        and v.snapshot_ts_utc < timestamp(date_add({{ last }}, interval 2 day))
        and v.is_available
        and v.form_factor in ('scooter', 'bicycle')
),
denver as (
    select st_union_agg(geom) as geom
    from {{ ref('dim_tract') }}
    where geom is not null
),
stops as (
    select s.stop_id, s.geom
    from {{ ref('dim_stop') }} as s
    cross join denver as d
    where s.is_current and st_contains(d.geom, s.geom)
),
counts as (
    select s.stop_id, v.snapshot_ts_utc, v.form_factor, count(*) as n_available
    from stops as s
    join vehicles as v
        on st_dwithin(s.geom, v.geom, 200)
    group by 1, 2, 3
),
grid as (
    -- Every stop, snapshot and form factor, so snapshots with none count as zero.
    select s.stop_id, n.snapshot_ts_utc, form_factor
    from stops as s
    cross join snapshots as n
    cross join unnest(['scooter', 'bicycle']) as form_factor
)

select
    {{ date_mst('g.snapshot_ts_utc') }} as date_mst,
    g.stop_id,
    {{ hour_mst('g.snapshot_ts_utc') }} as hour_mst,
    g.form_factor,
    count(*) as n_snapshots,
    round(avg(coalesce(c.n_available, 0)), 2) as avg_available_within_200m,
    avg(if(c.n_available is null, 1, 0)) as pct_snapshots_none_within_200m
from grid as g
left join counts as c
    on c.stop_id = g.stop_id
    and c.snapshot_ts_utc = g.snapshot_ts_utc
    and c.form_factor = g.form_factor
group by 1, 2, 3, 4
