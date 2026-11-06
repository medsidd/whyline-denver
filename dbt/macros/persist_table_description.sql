{% macro persist_table_description() %}
{#
persist_docs sets a table's description only when dbt creates the table, and incremental models
are created once, so this post-hook sets it on every incremental build. It runs no SQL.
#}
    {%- if execute and model.config.materialized == 'incremental' and model.description -%}
        {%- do adapter.update_table_description(this.database, this.schema, this.identifier, model.description) -%}
    {%- endif -%}
{% endmacro %}
