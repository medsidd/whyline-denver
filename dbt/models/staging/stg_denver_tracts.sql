{{ config(materialized='view') }}

select
    geo_id as geoid,
    geom
from {{ source('public_geo', 'census_tracts') }}
where state_fips_code = '08'
  and county_fips_code = '031'
