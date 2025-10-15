{% macro generate_schema_name(custom_schema_name=none, node=none) -%}
    {%- if custom_schema_name is none or custom_schema_name == '' -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name }}
    {%- endif -%}
{%- endmacro %}
