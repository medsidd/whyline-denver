{% macro as_mst(ts_utc) %}
    DATETIME({{ ts_utc }}, "America/Denver")
{% endmacro %}

{% macro date_mst(ts_utc) %}
    DATE({{ ts_utc }}, "America/Denver")
{% endmacro %}

{% macro hour_mst(ts_utc) %}
    EXTRACT(HOUR FROM DATETIME({{ ts_utc }}, "America/Denver"))
{% endmacro %}

{% macro gtfs_time_to_ts(service_date, hhmmss, tz="America/Denver") %}
timestamp(
    datetime(
        date_add(
            {{ service_date }},
            interval cast(floor(
                safe_cast(split({{ hhmmss }}, ':')[offset(0)] as int64) / 24
            ) as int64) day
        ),
        time(
            mod(
                safe_cast(split({{ hhmmss }}, ':')[offset(0)] as int64),
                24
            ),
            safe_cast(split({{ hhmmss }}, ':')[offset(1)] as int64),
            safe_cast(split({{ hhmmss }}, ':')[offset(2)] as int64)
        )
    ),
    "{{ tz }}"
)
{% endmacro %}
