{% macro latest_extract_date(relation) %}
{#
Latest `_extract_date` of a bronze snapshot table, inlined as a DATE literal so BigQuery
prunes to one partition (a `(select max(...))` filter scans every partition). Falls back
to the subquery while parsing or when the table is not partitioned by extract date.
#}
    {%- set fallback = "(select max(_extract_date) from " ~ relation ~ ")" -%}
    {%- if not execute -%}
        {{ return(fallback) }}
    {%- endif -%}
    {%- set query -%}
        select max(parse_date('%Y%m%d', partition_id))
        from `{{ relation.database }}.{{ relation.schema }}.INFORMATION_SCHEMA.PARTITIONS`
        where table_name = '{{ relation.identifier }}'
          and regexp_contains(partition_id, r'^[0-9]{8}$')
    {%- endset -%}
    {%- set latest = run_query(query).columns[0].values()[0] -%}
    {{ return("date '" ~ latest ~ "'" if latest else fallback) }}
{% endmacro %}


{% macro recent_extracts_filter(relation, n) %}
{#
`_extract_date >= <date of the table's n-th most recent extract partition>` as a constant, so
BigQuery prunes while a bad latest load can still fall back to an earlier one. Unchanged
files are not reloaded, so counting partitions (not days) keeps every file covered.
#}
    {%- if not execute -%}
        {{ return('true') }}
    {%- endif -%}
    {%- set query -%}
        select min(extract_date) from (
            select parse_date('%Y%m%d', partition_id) as extract_date
            from `{{ relation.database }}.{{ relation.schema }}.INFORMATION_SCHEMA.PARTITIONS`
            where table_name = '{{ relation.identifier }}'
              and regexp_contains(partition_id, r'^[0-9]{8}$')
            order by extract_date desc
            limit {{ n }}
        )
    {%- endset -%}
    {%- set floor = run_query(query).columns[0].values()[0] -%}
    {{ return("_extract_date >= date '" ~ floor ~ "'" if floor else 'true') }}
{% endmacro %}


{% macro scd2_from_extracts(relation, key, attrs, sk_name) %}
{#
Type 2 versions of `key` from a silver model that keeps every GTFS extract (`_extract_date`).
A new version starts on the first extract where any of `attrs` changed. The first version is
backdated to 1900-01-01 so older facts resolve; a key missing from the latest extract keeps
its last version, ending on the last extract that contained it.
#}
{%- set attr_list = attrs | join(', ') -%}
with versions_in as (
    select
        {{ key }},
        _extract_date,
        {{ attr_list }},
        to_json_string(struct({{ attr_list }})) as attr_sig
    from {{ relation }}
),
flagged as (
    select
        *,
        if(attr_sig = lag(attr_sig) over (partition by {{ key }} order by _extract_date), 0, 1) as is_change
    from versions_in
),
numbered as (
    select
        *,
        sum(is_change) over (
            partition by {{ key }} order by _extract_date rows unbounded preceding
        ) as version_num
    from flagged
),
grouped as (
    select
        {{ key }},
        version_num,
        {%- for attr in attrs %}
        any_value({{ attr }}) as {{ attr }},
        {%- endfor %}
        min(_extract_date) as first_seen_extract,
        max(_extract_date) as last_seen_extract
    from numbered
    group by {{ key }}, version_num
),
bounded as (
    select
        *,
        if(version_num = 1, date '1900-01-01', first_seen_extract) as valid_from,
        lead(first_seen_extract) over (partition by {{ key }} order by version_num) as next_valid_from,
        max(last_seen_extract) over () as latest_extract
    from grouped
)
select
    farm_fingerprint(concat(cast({{ key }} as string), '|', cast(valid_from as string))) as {{ sk_name }},
    {{ key }},
    {{ attr_list }},
    valid_from,
    case
        when next_valid_from is not null then date_sub(next_valid_from, interval 1 day)
        when last_seen_extract = latest_extract then date '9999-12-31'
        else last_seen_extract
    end as valid_to,
    next_valid_from is null and last_seen_extract = latest_extract as is_current,
    next_valid_from is null as is_latest_version,
    first_seen_extract,
    last_seen_extract
from bounded
{% endmacro %}
