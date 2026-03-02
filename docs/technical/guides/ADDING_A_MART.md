# Adding a New Mart

This guide walks through adding a new analytics mart to WhyLine Denver and making it available in the dashboard.

---

## Overview

A mart is a Gold-layer dbt model that combines and aggregates data from staging and intermediate models into an analytics-ready table. Marts are the tables that the API queries and that users can access through the dashboard.

---

## Step 1: Determine the domain

Marts are organized under `dbt/models/marts/` by domain:

```
dbt/models/marts/
├── reliability/     time-series performance metrics
├── safety/          crash proximity and risk
├── equity/          vulnerability and access gaps
├── access/          sidewalk and physical infrastructure
└── mart_gtfs_*.sql  reference tables (stops, routes)
```

Place your new mart in the appropriate domain folder, or create a new one if the domain is genuinely new.

---

## Step 2: Choose the materialization

| Pattern | When to use | Example |
|---------|------------|---------|
| `incremental` (partitioned by service_date_mst) | Time-series data that grows daily | mart_reliability_by_route_day |
| `table` (snapshot) | Static analysis refreshed on each dbt run | mart_crash_proximity_by_stop |
| `view` | Rarely — only if the mart is trivially cheap to recompute | — |

Most new marts should be snapshot `table`s unless they contain time-series data.

---

## Step 3: Write the SQL model

Create `dbt/models/marts/{domain}/mart_your_metric.sql`:

### Snapshot mart template

```sql
{{
    config(
        materialized='table',
        meta={'allow_in_app': true}
    )
}}

with stops as (
    select stop_id, stop_lat, stop_lon, geom
    from {{ ref('stg_gtfs_stops') }}
),

source_data as (
    select ...
    from {{ ref('stg_your_source') }}
),

-- your logic here

final as (
    select
        s.stop_id,
        -- computed metrics
        current_date() as build_run_at
    from stops s
    left join ...
)

select * from final
```

### Incremental (time-series) mart template

```sql
{{
    config(
        materialized='incremental',
        unique_key=['col_a', 'service_date_mst'],
        partition_by={'field': 'service_date_mst', 'data_type': 'date'},
        cluster_by=['route_id'],
        incremental_strategy='insert_overwrite',
        meta={'allow_in_app': true}
    )
}}

with events as (
    select *
    from {{ ref('int_rt_events_resolved') }}

    {% if is_incremental() %}
    where service_date_mst >= date_sub(current_date(), interval {{ var('weather_lookback_days', 30) }} day)
    {% endif %}
),

...
```

**Critical**: The `meta: {allow_in_app: true}` config is what makes the mart visible to the API. Without it, the table cannot be queried from the dashboard.

---

## Step 4: Document in schema.yml

Add to `dbt/models/marts/schema.yml` (or the domain-specific schema file):

```yaml
models:
  - name: mart_your_metric
    description: >
      One sentence describing what this mart contains and why it exists.
    meta:
      allow_in_app: true
    columns:
      - name: stop_id
        description: "Transit stop identifier. Joins to mart_gtfs_stops."
        tests:
          - not_null
          - relationships:
              to: ref('mart_gtfs_stops')
              field: stop_id
      - name: your_score
        description: "0–100 normalized score. Higher = ..."
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100
```

---

## Step 5: Run and test

```bash
# Run the new mart
dbt run --select mart_your_metric

# Run tests
dbt test --select mart_your_metric

# Verify in BigQuery
dbt run --select mart_your_metric+ --full-refresh  # force full recompute
```

---

## Step 6: Export to DuckDB

Add the new mart to the export and sync lists in `src/whyline/sync/export_bq_marts.py`:

```python
HOT_MARTS = {
    "mart_reliability_by_route_day",
    "mart_reliability_by_stop_hour",
    # ... existing marts ...
    "mart_your_metric",          # add here
}

# If snapshot (not time-series):
LATEST_RUN_DATE_ONLY_MARTS = {
    # ... existing snapshot marts ...
    "mart_your_metric",          # add here for snapshots
}
```

Then run:

```bash
make sync-export     # Export to GCS Parquet
make sync-refresh    # Load into DuckDB
```

---

## Step 7: Verify in the API

After syncing, the mart should appear in `/api/models`:

```bash
curl http://localhost:8000/api/models | jq '.models[].name'
```

You can now query it by name in the dashboard, either via natural language or by writing SQL directly.

If the mart contains `stop_id` or `route_id` columns, query results will automatically be enriched with stop names, coordinates, and route names.

---

## Step 8: Add to downloads

If you want the mart available in the "Download Mart" panel, add it to `ALLOWED_MARTS` in `api/routers/downloads.py`:

```python
ALLOWED_MARTS = {
    "mart_reliability_by_route_day",
    # ... existing ...
    "mart_your_metric",
}
```

---

## Checklist

- [ ] SQL model in `dbt/models/marts/{domain}/mart_your_metric.sql`
- [ ] `meta: {allow_in_app: true}` in config block
- [ ] Model documented in `schema.yml` with column descriptions
- [ ] dbt tests defined and passing
- [ ] Added to `HOT_MARTS` in `export_bq_marts.py`
- [ ] Added to `LATEST_RUN_DATE_ONLY_MARTS` if snapshot
- [ ] Synced to DuckDB and verified via `/api/models`
- [ ] Added to `ALLOWED_MARTS` in downloads router (if applicable)
