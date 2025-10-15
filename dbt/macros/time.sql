{% macro as_mst(ts_utc) %}
    DATETIME({{ ts_utc }}, "America/Denver")
{% endmacro %}

{% macro date_mst(ts_utc) %}
    DATE({{ ts_utc }}, "America/Denver")
{% endmacro %}

{% macro hour_mst(ts_utc) %}
    EXTRACT(HOUR FROM DATETIME({{ ts_utc }}, "America/Denver"))
{% endmacro %}
