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
(
  with parts as (
    select
      cast(split({{ hhmmss }}, ':')[offset(0)] as int64) as h,
      cast(split({{ hhmmss }}, ':')[offset(1)] as int64) as m,
      cast(split({{ hhmmss }}, ':')[offset(2)] as int64) as s
  )
  select
    timestamp(datetime(
      date_add({{ service_date }}, interval floor(h/24) day),
      time(mod(h,24), m, s)
    ), "{{ tz }}")
  from parts
)
{% endmacro %}
