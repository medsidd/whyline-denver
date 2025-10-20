{% test accepted_range(model, column_name, min_value=None, max_value=None, exclusive_min=False, exclusive_max=False) %}
    select
        {{ column_name }} as value
    from {{ model }}
    where 1 = 1
    {%- if min_value is not none %}
        and {{ column_name }} {{ '<=' if exclusive_min else '<' }} {{ min_value }}
    {%- endif %}
    {%- if max_value is not none %}
        and {{ column_name }} {{ '>=' if exclusive_max else '>' }} {{ max_value }}
    {%- endif %}
{% endtest %}
