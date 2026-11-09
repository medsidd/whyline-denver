{{ config(materialized='table', meta={"allow_in_app": false}) }}

{#
Route lines for the dashboard's result maps: dim_route_shape simplified to about 10 m, as
GeoJSON. Served by /api/routes/shapes, not queryable from the dashboard. Simplifying can
split a line, so geojson is a LineString or a MultiLineString.
#}
select
    route_id,
    direction_id,
    shape_id,
    n_trips,
    st_asgeojson(st_simplify(geom, 10)) as geojson,
    current_timestamp() as build_run_at
from {{ ref('dim_route_shape') }}
