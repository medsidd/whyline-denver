{% macro safe_int(value) %}
    SAFE_CAST({{ value }} AS INT64)
{% endmacro %}

{% macro safe_float(value) %}
    SAFE_CAST({{ value }} AS FLOAT64)
{% endmacro %}
