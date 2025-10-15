{% macro make_point(lon, lat) %}
    ST_GEOGPOINT(CAST({{ lon }} AS FLOAT64), CAST({{ lat }} AS FLOAT64))
{% endmacro %}
