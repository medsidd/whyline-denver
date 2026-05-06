# Project Requirements Document: Dimensional Modeling Rework
**Project:** Whyline Denver — Full Architecture Rework to Dimensional Model  
**Date:** 2026-05-06  
**Revision:** 11 (final)

---

## 1. Context & Problem Statement

The current mart layer is 9 denormalized, domain-isolated tables. Each mart embeds its own subset of stop/route/weather attributes rather than referencing shared, conformed dimensions. This causes:

- **No canonical dimensions** — stop attributes scatter across `mart_gtfs_stops`, `mart_reliability_by_stop_hour`, `mart_crash_proximity_by_stop`, etc.
- **Tight coupling** — `mart_priority_hotspots` hard-codes joins to 3 other marts; weights `0.5/0.3/0.2` are literals in `mart_priority_hotspots.sql:50`.
- **AI hallucination risk** — schema brief lists columns with no JOIN hints; LLM guesses table relationships.
- **Wrong BQ dataset for new layers** — `_qualify_bigquery_tables()` in `llm.py:205` hardcodes `BQ_DATASET_MART` for all table names. New `dim_*` tables in `stg_denver` would silently route to the wrong dataset.
- **Exporter assumes one dataset** — `export_bq_marts.py:50` sets `self.dataset = settings.BQ_DATASET_MART`; cannot export from `stg_denver`.
- **Frontend download options are hardcoded** — `DownloadPanel.tsx:8` static `MART_OPTIONS`.
- **Hardcoded Makefile selectors** — `dbt-run-realtime` (Makefile:234) lists old mart names explicitly.
- **Exposures.yml references old models** — `dbt/models/exposures.yml:14-20` depends on 7 old mart names.
- **Tests reference old mart names** — `tests/semantics/test_dbt_artifacts.py:25-33`, `tests/llm/test_llm.py`.
- **`ModelInfo` lacks `layer`** — `api/models.py:65` and `frontend/src/types/api.ts:35` have no layer field.

---

## 2. Goals

1. **Dimensional model** — Conformed `dim_*` tables, atomic `fct_*` facts, pre-aggregated `agg_*` rollups, and business-facing `mart_*` semantic outputs.
2. **Modularity** — New ingestors add only staging + dimension/fact models. No existing model is touched.
3. **AI accuracy** — FK and join-hint metadata in schema YAML surfaces in the layer-aware schema brief.
4. **Typed registry drives everything** — One `MartEntry` per table controls: logical dataset key, partition column, sync/export inclusion, DuckDB materialization mode, and three exposure flags (`allow_prompt`, `allow_sql`, `allow_download`).
5. **Frontend downloads driven by API** — `DownloadPanel.tsx` fetches `/api/downloads/options`.
6. **Non-breaking migration** — Old mart files are overwritten in-place with explicit-column compat views. Deprecated entries stay `allow_sql=True`; DuckDB gets alias views for them. Old names absent from schema brief on day 1.

### Non-Goals
- Changing ingest source systems or raw BigQuery tables.
- Rebuilding the frontend URL structure or API paths.
- Moving away from dbt, BigQuery, or DuckDB.

---

## 3. Current State (Baseline)

### dbt layers
```
staging/        (10 models)   stg_* — clean/dedup raw sources
intermediate/   (6 models)    int_* — joins, headways, schedule expansion
marts/          (9 models)    mart_* — flat domain aggregations; 2 are reference lookups
```

### Hardcoded items that must change

| File | Location | Problem |
|------|----------|---------|
| `llm.py` | line 205 | `BQ_DATASET_MART` hardcoded for all table qualification |
| `export_bq_marts.py` | lines 23, 50 | `PARTITIONED_MARTS` frozenset separate; single dataset |
| `DownloadPanel.tsx` | line 8 | Static `MART_OPTIONS` |
| `mart_priority_hotspots.sql` | line 50 | `0.5/0.3/0.2` literal weights |
| `Makefile` | line 234 | `dbt-run-realtime` lists old mart names |
| `dbt/models/exposures.yml` | lines 14-20 | 7 old mart `depends_on` refs |
| `tests/semantics/test_dbt_artifacts.py` | lines 25-33 | Expected old mart names |
| `tests/llm/test_llm.py` | lines 8-28 | Old mart name in SQL test fixtures |
| `api/models.py` | line 65 | `ModelInfo` lacks `layer` field |
| `frontend/src/types/api.ts` | line 35 | `ModelInfo` lacks `layer` field |

---

## 4. Target Architecture

### Layer structure
```
staging/         stg_*   — unchanged
intermediate/    int_*   — unchanged + feed_ts_utc added to int_rt_events_resolved (pre-work)
dimensions/      dim_*   — NEW: conformed entity attributes (logical dataset key: "stg")
facts/           fct_*   — NEW: atomic event-level records (logical dataset key: "stg")
aggregates/      agg_*   — RENAMED: pre-aggregated rollups (logical dataset key: "mart")
marts/           mart_*  — Business-facing semantic marts: domain scores + composite (logical dataset key: "mart")
```

### Dataset routing

All YAML `meta.layer` values use exactly: `dim`, `fct`, `agg`, `mart`. No other strings.

| Prefix | Logical key | Resolved to (via Settings) |
|--------|-------------|---------------------------|
| `dim_`, `fct_` | `"stg"` | `BQ_DATASET_STG` (e.g. `stg_denver`) |
| `agg_`, `mart_` | `"mart"` | `BQ_DATASET_MART` (e.g. `mart_denver`) |

---

## 5. Intermediate Pre-Work (before Phase 1)

**Problem:** `int_rt_events_resolved` drops `feed_ts_utc`. The fact table needs it as part of the unique grain.

**Fix:** `int_rt_events_resolved` already selects from `stg_rt_events` in the `base` CTE. Add `feed_ts_utc` to that SELECT:
```sql
-- int_rt_events_resolved.sql — add to the base CTE
feed_ts_utc,       -- carried from stg_rt_events for fact table use
```
This is an additive view change. All existing downstream aggregations (which don't reference `feed_ts_utc`) are unaffected.

**Also note:** `stop_id` can be NULL in `stg_rt_events` (vehicle position records may not have stop context). The fact table unique grain must reflect this.

---

## 6. Dimensional Model Design

### Dimension Tables — `dimensions/`, logical key `"stg"`

**`dim_stop`** — Replaces `mart_gtfs_stops`
- PK: `stop_id`
- Columns: `stop_id`, `stop_name`, `lat`, `lon`, `wheelchair_boarding` — **no `geom` column**
- `geom` is intentionally excluded from `dim_stop` to avoid cross-engine schema drift: `dim_stop` is `allow_sql=True` and synced to DuckDB, but BigQuery GEOGRAPHY types cannot be stored in Parquet. Domain marts that require spatial joins (`mart_stop_safety`, `mart_stop_equity`, `mart_stop_access`) source from `stg_gtfs_stops.geom` directly (which is never app-exposed or synced to DuckDB). No `export_geom` flag needed on this entry.
- Source: `stg_gtfs_stops`

**`dim_route`** — Replaces `mart_gtfs_routes`
- PK: `route_id`
- Columns: `route_id`, `route_name`, `route_long_name`, `route_type`, `route_desc`
- Source: `stg_gtfs_routes`

**`dim_date`** — Calendar date spine (new)
- PK: `service_date_mst`
- Columns: `service_date_mst`, `day_of_week`, `day_name`, `is_weekend`, `month_num`, `month_name`, `quarter`, `year`, `season`
- Built with existing `{{ gtfs_date_spine() }}` macro (wraps BigQuery `generate_date_array`) — **no `dbt_utils` needed**
- **Date range policy:** controlled by dbt vars:
  ```yaml
  vars:
    dim_date_start: "2022-01-01"      # project epoch; fixed
    dim_date_end_offset_days: 365     # extend 1 year beyond current_date
  ```

**`dim_weather`** — Daily weather (new)
- PK: `service_date_mst` — must be unique; duplicates arise when `weather_station` var is unset and multiple stations exist for the same date.
- **Duplicate policy:** `weather_station` var is **required** for `dim_weather`. Use an explicit compiler error at the top of the model:
  ```sql
  {% if var('weather_station', none) is none %}
    {{ exceptions.raise_compiler_error(
       "dim_weather requires 'weather_station' dbt variable. "
       "Set it in dbt_project.yml vars or --vars '{weather_station: USW00023062}'"
    ) }}
  {% endif %}
  ```
- Columns: `service_date_mst`, `snow_day`, `precip_bin`, `tmin_c`, `tmax_c`, `tavg_c`, `snow_mm`, `precip_mm`
- Source: **`stg_weather`** directly with `WHERE station = '{{ var("weather_station") }}'` (NOT `int_weather_by_date` — that model only has `snow_day` and `precip_bin`; temperatures require `stg_weather`)
- `int_weather_by_date` is NOT deleted; other intermediate models reference it

**`dim_census_tract`** — Merged tract + ACS (new)
- PK: `geoid`
- **GEOID normalization:** The current `mart_vulnerability_by_stop.sql:17` applies `regexp_replace(geoid, '^14000US', '')` on the tracts side before joining ACS. However, the source of the prefix (tracts vs ACS) should be verified against live data before assuming. `dim_census_tract` normalizes both sides to a common key to be safe:
  ```sql
  -- tracts side
  regexp_replace(t.geoid, '^14000US', '') as geoid_norm
  -- ACS side
  regexp_replace(a.geoid, '^14000US', '') as geoid_norm
  -- join on geoid_norm
  ```
  The PK exposed is `geoid` — the normalized plain Census FIPS code (e.g. `08031000100`), with the `14000US` prefix stripped from both sides before joining. Downstream marts join on this `geoid` column.
- Columns: `geoid` (PK, normalized FIPS), `name`, `aland_m2`, `geom`, `pct_hh_no_vehicle`, `pct_transit_commute`, `pct_poverty`, `pop_total`
- `geom` for BigQuery spatial joins only; excluded from parquet
- `allow_prompt: false` — internal use only; not synced to DuckDB

---

### Fact Tables — `facts/`, logical key `"stg"`

**`fct_transit_events`**
- Source: `int_rt_events_resolved` (after pre-work adds `feed_ts_utc`)
- `stop_id` may be NULL for vehicle-position-only records. A NULL-containing column must not be used directly in a BigQuery MERGE `unique_key` (NULLs break the merge join).
- **Grain precision:** each row is a (GTFS-RT feed snapshot, trip, stop observation). Not a pure stop-event — it is a realtime feed/trip snapshot with optional stop context. Name and document it as such.
- **Unique key:** use `TO_HEX(SHA256(...))` for collision-resistant string ID (preferred over `FARM_FINGERPRINT` which is 64-bit and has non-negligible birthday collision risk at scale). Cast every component to STRING explicitly:
  ```sql
  TO_HEX(SHA256(CONCAT(
      CAST(feed_ts_utc AS STRING),
      '|', CAST(trip_id AS STRING),
      '|', COALESCE(CAST(stop_id AS STRING), '__null__')
  ))) AS transit_event_id
  ```
  dbt incremental config: `unique_key: transit_event_id`
- Run a BigQuery `COUNT(*) != COUNT(DISTINCT transit_event_id)` check against `stg_rt_events` before committing. If collision rate > 0, add `CAST(event_ts_utc AS STRING)` to the concat.
- **FK to `dim_stop`:** marked `where: "stop_id is not null"` in schema YAML (conditional relationship test)
- Columns: `feed_ts_utc`, `route_id`, `trip_id`, `stop_id`, `direction_id`, `service_date_mst`, `event_hour_mst`, `event_ts_utc`, `delay_sec`, `delay_sec_raw`, `is_on_time`
- Materialization: incremental (partition: `service_date_mst`, cluster: `route_id, stop_id`)
- `allow_prompt: false, allow_sql: false, allow_download: false, sync_to_duckdb: false, export_to_gcs: false`

**`fct_headway_adherence`**
- Promotes `int_headway_adherence`
- `direction_id` can be NULL in source data; must not appear directly in a BigQuery MERGE `unique_key`.
- **Unique key:** surrogate hash `headway_event_id` — cast every component to STRING for type safety (direction_id may be INT64, NUMERIC, or STRING depending on schema evolution):
  ```sql
  TO_HEX(SHA256(CONCAT(
      CAST(route_id AS STRING),
      '|', COALESCE(CAST(direction_id AS STRING), '__null__'),
      '|', CAST(stop_id AS STRING),
      '|', CAST(service_date_mst AS STRING),
      '|', CAST(event_ts_utc AS STRING)
  ))) AS headway_event_id
  ```
  dbt incremental config: `unique_key: headway_event_id`
- Grain (logical): `(route_id, direction_id, stop_id, service_date_mst, event_ts_utc)` — uniqueness test required
- Columns: `route_id`, `direction_id`, `stop_id`, `service_date_mst`, `event_ts_utc`, `obs_headway_sec`, `sch_headway_sec`, `dt_abs`, `headway_adherent`
- Materialization: incremental (same config as current `int_headway_adherence`)
- `allow_prompt: false, allow_sql: false, allow_download: false, sync_to_duckdb: false, export_to_gcs: false`

---

### Aggregate Tables — `aggregates/`, logical key `"mart"`

**`agg_reliability_by_route_day`** — Renamed from `mart_reliability_by_route_day`
- Grain: `(route_id, service_date_mst, precip_bin, snow_day)` — unchanged
- Columns: `route_id`, `service_date_mst`, `precip_bin`, `snow_day`, `n_events`, `n_reported_events`, `pct_on_time`, `mean_delay_sec`, `median_delay_sec`, `p90_delay_sec`, `build_run_at`
- Weather denormalized for query convenience; schema YAML documents JOIN path to `dim_weather`
- Source: `fct_transit_events` (replacing direct `int_rt_events_resolved` reference)
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: false, partition_column: service_date_mst`

**`agg_reliability_by_stop_hour`** — Renamed from `mart_reliability_by_stop_hour`
- Grain: `(stop_id, service_date_mst, event_hour_mst)` — unchanged
- Columns: `stop_id`, `service_date_mst`, `event_hour_mst`, `n_events`, `pct_on_time`, `mean_delay_sec`, `p90_delay_sec`, `route_id_mode`, `headway_adherence_rate`, `obs_headway_sec_p50`, `obs_headway_sec_p90`, `build_run_at`
- Source: `fct_transit_events` + `fct_headway_adherence`
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: false, partition_column: service_date_mst`

**`agg_weather_impacts_by_route`** — Renamed from `mart_weather_impacts`
- Grain: `(route_id, precip_bin)` — unchanged
- Columns: `route_id`, `precip_bin`, `pct_on_time_avg`, `pct_on_time_normal`, `delta_pct_on_time`, `build_run_at`
- Source: `agg_reliability_by_route_day`
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

---

### Mart Tables — `marts/`, logical key `"mart"`

Marts are **business-facing semantic outputs**: domain score tables and the composite cross-domain priority mart.

**`mart_stop_reliability_score`** — Internal scoring helper (new, explicit)
- Grain: `stop_id`
- Columns: `stop_id`, `reliability_score_0_100`, `build_run_at`
- Logic: `100.0 * (1 - avg(pct_on_time))` over rolling 35-day window from `agg_reliability_by_stop_hour`
- Source: `agg_reliability_by_stop_hour`
- `allow_prompt: false, allow_sql: false, allow_download: false, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

**`mart_stop_safety`** — Renamed from `mart_crash_proximity_by_stop`; `crash_score_0_100` moved here
- Grain: `stop_id`
- Columns: `stop_id`, `as_of_date`, `window_days`, `crash_100m_cnt`, `severe_100m_cnt`, `fatal_100m_cnt`, `crash_250m_cnt`, `severe_250m_cnt`, `fatal_250m_cnt`, `crash_score_0_100`, `build_run_at`
- FK: `stop_id → dim_stop`
- **Spatial join source:** `stg_gtfs_stops` (for `geom`; `dim_stop` does not have `geom`). Use `stg_gtfs_stops.geom` for the ST_DWithin buffer join against crashes. Non-spatial stop attributes (`stop_name`, etc.) come from `dim_stop`. Pattern: the mart joins both sources and uses `dim_stop.stop_id` as the FK reference.
- Source: `stg_gtfs_stops` (geom) + `stg_denver_crashes`
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

**`mart_stop_access`** — Renamed from `mart_access_score_by_stop`
- Grain: `stop_id`
- Columns: `stop_id`, `buffer_m`, `sidewalk_len_m_within_200m`, `access_score_0_100`, `build_run_at`
- FK: `stop_id → dim_stop`
- **Spatial join source:** `stg_gtfs_stops` (for `geom`) + `stg_sidewalks` (for sidewalk `geom`). The ST_Buffer and ST_Intersects calls require `stg_gtfs_stops.geom`; `dim_stop` does not have `geom`. Same pattern as `mart_stop_safety`.
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

**`mart_stop_equity`** — Renamed from `mart_vulnerability_by_stop`
- Grain: `stop_id`
- Columns: `stop_id`, `pct_hh_no_vehicle_w`, `pct_transit_commute_w`, `pct_poverty_w`, `vuln_score_0_100`, `build_run_at`
- FKs: `stop_id → dim_stop`, spatial join → `dim_census_tract`
- **Spatial join source:** `stg_gtfs_stops` (for `geom`) + `dim_census_tract` (for geom + ACS attributes). Same pattern as `mart_stop_safety`: spatial geometry sourced from `stg_gtfs_stops`, not `dim_stop`.
- Source: `stg_gtfs_stops` (geom) + `dim_census_tract` (geom + ACS)
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

**`mart_stop_priority`** — Renamed from `mart_priority_hotspots`
- Grain: `stop_id`
- Columns: `stop_id`, `vuln_score_0_100`, `crash_score_0_100`, `reliability_score_0_100`, `priority_score`, `priority_rank`, `build_run_at`
- FK: `stop_id → dim_stop`
- Sources: `mart_stop_safety`, `mart_stop_equity`, `mart_stop_reliability_score`
- **Weights as dbt vars** (defaults preserve current values exactly):
  ```yaml
  vars:
    priority_weight_equity: 0.5
    priority_weight_safety: 0.3
    priority_weight_reliability: 0.2
  ```
  SQL: `{{ var('priority_weight_equity', 0.5) }} * coalesce(vuln_score_0_100, 0) + ...`
- `allow_prompt: true, allow_sql: true, allow_download: true, sync_to_duckdb: true, export_to_gcs: true, duckdb_hot: true, latest_only: true`

---

## 7. Typed Registry: `MartEntry`

All fields are keyword-only (no positional boolean chains) to prevent silent ordering bugs:

```python
# src/whyline/sync/constants.py
from dataclasses import dataclass, KW_ONLY
from typing import Literal, Optional

@dataclass(frozen=True)
class MartEntry:
    name: str
    layer: Literal["dim", "fct", "agg", "mart"]
    bq_dataset: Literal["stg", "mart"]  # logical key; resolved via Settings at runtime
    _: KW_ONLY
    allow_prompt: bool       # included in LLM schema brief
    allow_sql: bool          # accepted by SQL guardrails and BQ qualification map
    allow_download: bool     # visible in /api/downloads/options
    download_label: str      # human-readable label; empty string if not downloadable
    sync_to_duckdb: bool     # included in DuckDB refresh
    export_to_gcs: bool      # exported to GCS parquet
    duckdb_hot: bool         # materialized as DuckDB table (vs view); only meaningful if sync_to_duckdb=True
    latest_only: bool        # export only the latest run_date partition; only meaningful if export_to_gcs=True
    partition_column: Optional[str] = None
    export_geom: bool = False
    deprecated: bool = False   # compat view; allow_sql=True; absent from brief and downloads

def resolve_bq_dataset(entry: "MartEntry", settings) -> str:
    return settings.BQ_DATASET_STG if entry.bq_dataset == "stg" else settings.BQ_DATASET_MART

MART_REGISTRY: list[MartEntry] = [
    # --- Dimensions ---
    MartEntry("dim_stop",  "dim", "stg",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Stops reference",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("dim_route", "dim", "stg",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Routes reference",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("dim_date",  "dim", "stg",
              allow_prompt=True,  allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("dim_weather", "dim", "stg",
              allow_prompt=True,  allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    # dim_census_tract: BigQuery-only (spatial joins at mart build time); not in DuckDB or GCS
    MartEntry("dim_census_tract", "dim", "stg",
              allow_prompt=False, allow_sql=False, allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
              # latest_only=False: latest_only is only meaningful when export_to_gcs=True

    # --- Facts (BigQuery-only; too large for DuckDB; allow_sql=False so LLM cannot query) ---
    MartEntry("fct_transit_events", "fct", "stg",
              allow_prompt=False, allow_sql=False, allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False,
              partition_column="service_date_mst"),
    MartEntry("fct_headway_adherence", "fct", "stg",
              allow_prompt=False, allow_sql=False, allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False,
              partition_column="service_date_mst"),

    # --- Aggregates ---
    MartEntry("agg_reliability_by_route_day", "agg", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Reliability by route & day",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=False,
              partition_column="service_date_mst"),
    MartEntry("agg_reliability_by_stop_hour", "agg", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Reliability by stop & hour",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=False,
              partition_column="service_date_mst"),
    MartEntry("agg_weather_impacts_by_route", "agg", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Weather impacts by route",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),

    # --- Marts ---
    MartEntry("mart_stop_reliability_score", "mart", "mart",
              allow_prompt=False, allow_sql=False, allow_download=False, download_label="",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("mart_stop_safety", "mart", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Stop safety scores",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("mart_stop_access", "mart", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Stop access scores",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("mart_stop_equity", "mart", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Stop equity scores",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),
    MartEntry("mart_stop_priority", "mart", "mart",
              allow_prompt=True,  allow_sql=True,  allow_download=True,  download_label="Stop priority ranking",
              sync_to_duckdb=True,  export_to_gcs=True,  duckdb_hot=True,  latest_only=True),

    # --- Deprecated compat views ---
    # bq_dataset="mart": compat view files live in marts/ dbt folder → mart_denver dataset
    # even when they point to stg_denver dim tables
    # Deprecated entries: export_to_gcs=False → latest_only=False (invariant)
    MartEntry("mart_gtfs_stops",  "dim", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_gtfs_routes", "dim", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_reliability_by_route_day", "agg", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_reliability_by_stop_hour", "agg", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_weather_impacts", "agg", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_crash_proximity_by_stop", "mart", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_access_score_by_stop", "mart", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_vulnerability_by_stop", "mart", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
    MartEntry("mart_priority_hotspots", "mart", "mart", deprecated=True,
              allow_prompt=False, allow_sql=True,  allow_download=False, download_label="",
              sync_to_duckdb=False, export_to_gcs=False, duckdb_hot=False, latest_only=False),
]

MART_BY_NAME: dict[str, MartEntry] = {e.name: e for e in MART_REGISTRY}

# ── Phase 1 (Dimensions): MART_BY_NAME is the only export used by sync/export code.
#    The API-facing derived constants below are NOT added to constants.py until Phase 5.
#    ALLOWLISTED_MARTS stays as a hardcoded 9-name tuple (unchanged from today) through Phase 4,
#    so the API layer — guardrails, schema brief, /api/models — sees only the current 9 mart names
#    and cannot accidentally reference dim_*/agg_*/mart_stop_* that don't yet exist in BigQuery.
#
# ── Phase 5 (API cutover): replace the hardcoded ALLOWLISTED_MARTS tuple with the derived
#    constants below. Import sites in deps.py, sql_guardrails.py, llm.py switch simultaneously.

# --- Added in Phase 5 ---
PROMPT_MARTS         = tuple(e.name for e in MART_REGISTRY if e.allow_prompt)
GUARDRAIL_MARTS      = tuple(e.name for e in MART_REGISTRY if e.allow_sql)
DOWNLOAD_MARTS       = tuple(e.name for e in MART_REGISTRY if e.allow_download and not e.deprecated)
EXPORT_MARTS         = tuple(e.name for e in MART_REGISTRY if e.export_to_gcs)
SYNC_MARTS           = tuple(e.name for e in MART_REGISTRY if e.sync_to_duckdb)
# ALLOWLISTED_MARTS replaces the old hardcoded tuple; defined after GUARDRAIL_MARTS.
ALLOWLISTED_MARTS    = GUARDRAIL_MARTS
HOT_MARTS            = {e.name for e in MART_REGISTRY if e.duckdb_hot and e.sync_to_duckdb}
LATEST_RUN_DATE_ONLY = {e.name for e in MART_REGISTRY if e.latest_only and e.export_to_gcs}
PARTITIONED_MARTS    = frozenset(e.name for e in MART_REGISTRY if e.partition_column and e.export_to_gcs)

# Registry invariant tests (run in conftest.py or a dedicated test file):
# 1. If sync_to_duckdb=True → export_to_gcs=True (can't DuckDB-refresh what was never exported)
#    Exception: entries explicitly marked alias-only can be sync_to_duckdb=False
# 2. If duckdb_hot=True → sync_to_duckdb=True
# 3. If latest_only=True → export_to_gcs=True
# 4. If allow_download=True → download_label != ""
# 5. If deprecated=True → allow_prompt=False and allow_download=False
```

---

## 8. Three Model Maps in `DbtArtifacts`

`_all_models()` must load ALL models present in the dbt manifest that also appear in `MART_BY_NAME` — with **no filtering on `meta.allow_in_app`**. The three public methods then apply their respective filters:

```python
# semantics/dbt_artifacts.py

@dataclass
class RelationshipHint:
    to_model: str
    join_on: str

@dataclass
class ModelInfo:
    name: str
    fq_name: str
    description: str
    layer: str                             # exactly "dim" | "fct" | "agg" | "mart"
    columns: dict[str, ColumnInfo]
    relationships: list[RelationshipHint]  # from meta.relationships
    # layer resolution priority:
    # 1. meta.layer from schema YAML (authoritative for active models)
    # 2. MART_BY_NAME[name].layer from registry (fallback for deprecated/compat models
    #    whose YAML meta.layer may be stale or absent after the compat view overwrite)

class DbtArtifacts:
    def _all_models(self) -> dict[str, ModelInfo]:
        """Load every model from manifest that appears in MART_BY_NAME. No allow_in_app filter."""
        # Previously filtered by meta.allow_in_app — remove that filter entirely.
        # Filtering is now done by the caller via the three methods below.
        #
        # Missing-model behavior (phased rollout):
        # - Phases 1–4: registry entries not yet present in the manifest are SKIPPED with a
        #   LOGGER.warning (e.g. "dim_stop not found in manifest — skipping"). This lets
        #   sync/export code run against the registry before all dbt models are built.
        # - Phase 5 (API cutover): on startup, call validate_registry_completeness() which
        #   raises RuntimeError if any entry where allow_prompt=True or allow_sql=True is
        #   absent from the manifest. Controlled by the STRICT_MODEL_VALIDATION env var
        #   (default False in development; set True in Cloud Run api-service at Phase 5 deploy).
        ...

    def validate_registry_completeness(self) -> None:
        """Fail loudly at startup if any prompt/sql model is absent from the manifest.
        Called only when STRICT_MODEL_VALIDATION=1 (Phase 5 cutover and beyond).
        """
        manifest_names = set(self._all_models().keys())
        required = {e.name for e in MART_REGISTRY if e.allow_prompt or e.allow_sql}
        missing = required - manifest_names
        if missing:
            raise RuntimeError(
                f"STRICT_MODEL_VALIDATION: required models absent from manifest: "
                f"{', '.join(sorted(missing))}. Run `dbt run` to build missing models."
            )

    def prompt_models(self) -> dict[str, ModelInfo]:
        """For LLM schema brief: allow_prompt=True."""
        return {n: m for n, m in self._all_models().items() if n in set(PROMPT_MARTS)}

    def sql_models(self) -> dict[str, ModelInfo]:
        """For guardrails + BQ qualification: allow_sql=True (includes deprecated)."""
        return {n: m for n, m in self._all_models().items() if n in set(GUARDRAIL_MARTS)}

    def download_models(self) -> dict[str, ModelInfo]:
        """For /api/downloads/options: allow_download=True, not deprecated."""
        return {n: m for n, m in self._all_models().items() if n in set(DOWNLOAD_MARTS)}

    # Keep allowed_models() as an alias for sql_models() during transition
    def allowed_models(self) -> dict[str, ModelInfo]:
        return self.sql_models()
```

`api/deps.py` updates — **there is NO generic `get_models()`**. Each call site must name an explicit map:
- `GET /api/models` endpoint handler → `dbt.prompt_models()` — exposes only `allow_prompt=True` entries; deprecated SQL-only compat entries are never returned here
- `get_schema_brief()` → `dbt.prompt_models()`
- `get_guardrail_config(engine)` → allowlist derived from `dbt.sql_models()` (accepts deprecated names)
- `get_qualification_models(engine)` (for BQ `_qualify_bigquery_tables`) → `dbt.sql_models()` (includes deprecated so old cached SQL qualifies correctly)
- Add a FastAPI startup event handler that calls `DbtArtifacts().validate_registry_completeness()` when `STRICT_MODEL_VALIDATION=1`. Set this env var in the Cloud Run `api-service` deployment at the Phase 5 deploy step. Do not set it in local development (default `False`) or in Phases 1–4.

The key invariant: `prompt_models()` and `sql_models()` are always called at separate, named call sites. Any code that only needs one of them must NOT use the other as a substitute.

`src/whyline/engines/bigquery_engine.py:26-27` — `_allowed_models()` currently calls `DbtArtifacts().allowed_models()`. With the alias in place this continues to work; but explicitly update to `DbtArtifacts().sql_models()` for clarity:
```python
# bigquery_engine.py
def _allowed_models():
    return DbtArtifacts().sql_models()   # was: .allowed_models()
```

---

## 9. BQ Dataset Routing Fix (`llm.py:192`)

`ModelInfo.fq_name` is already populated from the dbt manifest `node.relation_name` (e.g. `whyline-denver.stg_denver.dim_stop`). Use it directly:

```python
def _qualify_bigquery_tables(sql: str, models: Mapping[str, ModelInfo]) -> str:
    cte_names = {name.strip("`").lower() for name in CTE_PATTERN.findall(sql)}

    def replacer(match: re.Match[str]) -> str:
        raw_table = match.group("table").strip("`")
        alias = match.group("alias") or ""
        if raw_table.lower() in cte_names or "." in raw_table:
            return match.group(0)
        model = models.get(raw_table)
        if model and model.fq_name:
            qualified = f"`{model.fq_name}`"   # fq_name carries correct dataset
        else:
            qualified = f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET_MART}.{raw_table}`"
        return f"{match.group('clause')} {qualified}{alias}"

    return TABLE_PATTERN.sub(replacer, sql)
```

Pass `sql_models()` (not `prompt_models()`) to `_qualify_bigquery_tables` so deprecated table names also qualify correctly.

---

## 10. Exporter Fix (`export_bq_marts.py`)

- `PARTITIONED_MARTS` frozenset on line 23: delete; use `PARTITIONED_MARTS` from constants.
- `self.dataset` (line 50) serves two purposes — **do not simply remove it**. Split into two:
  - `self.state_dataset = settings.BQ_DATASET_MART` — constant; the export state table always lives in `mart_denver`
  - `self._source_dataset(mart_name)` — per-mart lookup:
    ```python
    def _source_dataset(self, mart_name: str) -> str:
        return resolve_bq_dataset(MART_BY_NAME[mart_name], self.settings)
    ```
  All existing references to `self.dataset` in state queries remain as `self.state_dataset`; all references used to build `FROM {dataset}.{mart_name}` in export SQL switch to `self._source_dataset(mart_name)`.
- Iterate `EXPORT_MARTS` (not `ALLOWLISTED_MARTS`) as the default mart list.
- Geometry exclusion in SELECT:
  ```python
  GEOM_COLS = {"geom", "centroid"}   # known GEOGRAPHY column names

  def _select_clause(self, entry: MartEntry) -> str:
      if entry.export_geom:
          return "*"
      known_geom = GEOM_COLS & self._column_names(entry.name)
      if known_geom:
          exclusions = ", ".join(sorted(known_geom))
          return f"* EXCEPT ({exclusions})"
      return "*"
  ```
  `_column_names` queries BQ schema for the table using `self._source_dataset(entry.name)`, not `self.state_dataset`.

---

## 11. DuckDB Deprecated Alias Views

In `refresh_duckdb.py`, after loading all active marts, create DuckDB views for deprecated entries with explicit column lists (matching Section 14) so old cached SQL validates AND executes without schema drift:

```python
DEPRECATED_DUCKDB_ALIASES: dict[str, str] = {
    "mart_gtfs_stops":
        "SELECT stop_id, stop_name, lat, lon FROM dim_stop",
    "mart_gtfs_routes":
        "SELECT route_id, route_name, route_long_name, route_type FROM dim_route",
    "mart_reliability_by_route_day":
        "SELECT route_id, service_date_mst, precip_bin, snow_day, n_events, n_reported_events, "
        "pct_on_time, mean_delay_sec, median_delay_sec, p90_delay_sec, build_run_at "
        "FROM agg_reliability_by_route_day",
    "mart_reliability_by_stop_hour":
        "SELECT stop_id, service_date_mst, event_hour_mst, n_events, pct_on_time, "
        "mean_delay_sec, p90_delay_sec, route_id_mode, headway_adherence_rate, "
        "obs_headway_sec_p50, obs_headway_sec_p90, build_run_at "
        "FROM agg_reliability_by_stop_hour",
    "mart_weather_impacts":
        "SELECT route_id, precip_bin, pct_on_time_avg, pct_on_time_normal, "
        "delta_pct_on_time, build_run_at FROM agg_weather_impacts_by_route",
    "mart_crash_proximity_by_stop":
        "SELECT stop_id, as_of_date, window_days, crash_100m_cnt, severe_100m_cnt, "
        "fatal_100m_cnt, crash_250m_cnt, severe_250m_cnt, fatal_250m_cnt, build_run_at "
        "FROM mart_stop_safety",
    "mart_access_score_by_stop":
        "SELECT stop_id, buffer_m, sidewalk_len_m_within_200m, access_score_0_100, build_run_at "
        "FROM mart_stop_access",
    "mart_vulnerability_by_stop":
        "SELECT stop_id, pct_hh_no_vehicle_w, pct_transit_commute_w, pct_poverty_w, "
        "vuln_score_0_100, build_run_at FROM mart_stop_equity",
    "mart_priority_hotspots":
        "SELECT stop_id, vuln_score_0_100, crash_score_0_100, reliability_score_0_100, "
        "priority_score, priority_rank, build_run_at FROM mart_stop_priority",
}

for alias, select_sql in DEPRECATED_DUCKDB_ALIASES.items():
    con.execute(f"CREATE OR REPLACE VIEW {alias} AS {select_sql}")
```

---

## 12. Frontend & API Changes

### `GET /api/downloads/options` (new endpoint)
```python
# api/routers/downloads.py
@router.get("/options")
def list_download_options() -> list[dict]:
    return [
        {"value": e.name, "label": e.download_label}
        for e in MART_REGISTRY
        if e.allow_download and e.download_label and not e.deprecated
    ]
```

### `POST /api/downloads/mart` — add `DOWNLOAD_MARTS` server-side validation
The existing `download_mart()` handler currently validates only via `sanitize_sql()` (guardrail allowlist). Add an explicit check against `DOWNLOAD_MARTS` before building the SQL:
```python
if request.mart not in set(DOWNLOAD_MARTS):
    raise HTTPException(status_code=400, detail=f"Mart '{request.mart}' is not available for download")
```
This ensures deprecated and internal marts cannot be downloaded even if a client constructs a raw request, independent of what the UI presents.

### `ModelInfo` — add `layer` field
```python
# api/models.py
class ModelInfo(BaseModel):
    name: str
    fq_name: str
    description: str | None = None
    layer: str | None = None        # "dim" | "fct" | "agg" | "mart"
    columns: dict[str, ModelColumnInfo] = Field(default_factory=dict)
```

### `DownloadOption` — new response type
```python
# api/models.py
class DownloadOption(BaseModel):
    value: str    # mart name
    label: str    # human-readable label
```

### TypeScript updates (`frontend/src/types/api.ts`)
```typescript
export interface ModelInfo {
  name: string;
  fq_name: string;
  description: string | null;
  layer: string | null;            // "dim" | "fct" | "agg" | "mart"
  columns: Record<string, ModelColumnInfo>;
}

export interface DownloadOption {
  value: string;
  label: string;
}
```

### `DownloadPanel.tsx`
Replace static `MART_OPTIONS` with `useEffect` fetch:
```typescript
const [martOptions, setMartOptions] = useState<DownloadOption[]>([]);
useEffect(() => {
  fetch("/api/downloads/options").then(r => r.json()).then(setMartOptions);
}, []);
```

---

## 13. Schema YAML Standards

Model-level `meta` block (non-deprecated models only):
```yaml
config:
  meta:
    allow_in_app: true     # mirrors allow_prompt
    layer: agg             # exact value: dim | fct | agg | mart
    relationships:
      - to: dim_route
        join_on: route_id
      - to: dim_weather
        join_on: service_date_mst
```

FK column entries:
```yaml
- name: route_id
  description: "Foreign key to dim_route. JOIN dim_route ON route_id to get route_name."
  meta:
    fk_table: dim_route
    fk_column: route_id
```

Conditional FK test for nullable `stop_id` in fact tables (use `data_tests:` form matching the repo's existing YAML style; `where` goes under `config:`):
```yaml
- name: stop_id
  data_tests:
    - relationships:
        to: ref('dim_stop')
        field: stop_id
        config:
          where: "stop_id is not null"
```

Surrogate key tests — add both `not_null` and `unique` on each generated key:
```yaml
- name: transit_event_id
  data_tests:
    - not_null
    - unique
```

---

## 14. Compat View Column Contracts

Compat views use explicit column lists (not `SELECT *`) to preserve the exact API contract even as new dimensions gain columns:

| Old name | Points to | SELECT clause |
|----------|-----------|---------------|
| `mart_gtfs_stops` | `dim_stop` | `stop_id, stop_name, lat, lon` |
| `mart_gtfs_routes` | `dim_route` | `route_id, route_name, route_long_name, route_type` |
| `mart_reliability_by_route_day` | `agg_reliability_by_route_day` | `route_id, service_date_mst, precip_bin, snow_day, n_events, n_reported_events, pct_on_time, mean_delay_sec, median_delay_sec, p90_delay_sec, build_run_at` |
| `mart_reliability_by_stop_hour` | `agg_reliability_by_stop_hour` | `stop_id, service_date_mst, event_hour_mst, n_events, pct_on_time, mean_delay_sec, p90_delay_sec, route_id_mode, headway_adherence_rate, obs_headway_sec_p50, obs_headway_sec_p90, build_run_at` |
| `mart_weather_impacts` | `agg_weather_impacts_by_route` | `route_id, precip_bin, pct_on_time_avg, pct_on_time_normal, delta_pct_on_time, build_run_at` |
| `mart_crash_proximity_by_stop` | `mart_stop_safety` | `stop_id, as_of_date, window_days, crash_100m_cnt, severe_100m_cnt, fatal_100m_cnt, crash_250m_cnt, severe_250m_cnt, fatal_250m_cnt, build_run_at` |
| `mart_access_score_by_stop` | `mart_stop_access` | `stop_id, buffer_m, sidewalk_len_m_within_200m, access_score_0_100, build_run_at` |
| `mart_vulnerability_by_stop` | `mart_stop_equity` | `stop_id, pct_hh_no_vehicle_w, pct_transit_commute_w, pct_poverty_w, vuln_score_0_100, build_run_at` |
| `mart_priority_hotspots` | `mart_stop_priority` | `stop_id, vuln_score_0_100, crash_score_0_100, reliability_score_0_100, priority_score, priority_rank, build_run_at` |

---

## 15. Additional File Updates

### `dbt/models/exposures.yml`
Update `depends_on` to new model names; update description from "Streamlit" to "Next.js":
```yaml
depends_on:
  - ref('agg_reliability_by_route_day')
  - ref('agg_reliability_by_stop_hour')
  - ref('agg_weather_impacts_by_route')
  - ref('mart_stop_safety')
  - ref('mart_stop_access')
  - ref('mart_stop_equity')
  - ref('mart_stop_priority')
  - ref('dim_stop')
  - ref('dim_route')
```

### `Makefile`

All dbt selectors that currently reference `'staging marts'` or old mart names need to include the new layers in dependency order: `staging intermediate dimensions facts aggregates marts`.

Use explicit path selectors (`staging.* intermediate.* dimensions.* facts.* aggregates.* marts.*`) to avoid ambiguity with dbt's node-selection syntax. This form is unambiguous even in clean environments.

| Target | Lines | Current | Updated |
|--------|-------|---------|---------|
| `bq-load-historical` run | 155 | `'staging marts'` | `'staging.* intermediate.* dimensions.* facts.* aggregates.* marts.*'` |
| `bq-load-historical` test | 156 | `'marts'` | `'dimensions.* aggregates.* marts.*'` |
| `nightly-bq` run | 201 | `'staging marts'` | `'staging.* intermediate.* dimensions.* facts.* aggregates.* marts.*'` |
| `nightly-bq` test | 202 | `'marts'` | `'dimensions.* aggregates.* marts.*'` |
| `dbt-run-marts` | 222 | `'marts.*'` | `'aggregates.* marts.*'` |
| `dbt-test-marts` | 228 | `marts` | `'dimensions.* aggregates.* marts.*'` |
| `dbt-run-realtime` | 234 | lists 7 old mart names | `stg_rt_events int_rt_events_resolved int_headway_adherence int_stop_headways_observed int_weather_by_date dim_weather fct_transit_events fct_headway_adherence agg_reliability_by_stop_hour agg_reliability_by_route_day agg_weather_impacts_by_route` |
| `dbt-run-preflight` (calls `dbt-run-marts`) | 252 | inherits old | correct after fixing `dbt-run-marts` |

Add new convenience targets:
```makefile
dbt-run-dimensions:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'dimensions.*'

dbt-run-facts:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'facts.*'

dbt-run-aggregates:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'aggregates.*'
```

### Tests

**`tests/semantics/test_dbt_artifacts.py:25-33`** — update expected model names:
Replace the 9 old mart names with the new `PROMPT_MARTS` set: `dim_stop`, `dim_route`, `dim_date`, `dim_weather`, `agg_reliability_by_route_day`, `agg_reliability_by_stop_hour`, `agg_weather_impacts_by_route`, `mart_stop_safety`, `mart_stop_access`, `mart_stop_equity`, `mart_stop_priority`.

**`tests/llm/test_llm.py:8-28`** — update SQL fixture to use `agg_reliability_by_route_day`; update `ModelInfo` fixture to use new fq_name `whyline-denver.mart_denver.agg_reliability_by_route_day`.

---

## 16. Layer-Aware LLM Schema Brief

```
[dim] dim_route: Route reference (route_id PK, route_name, route_long_name, route_type)
[dim] dim_stop: Stop reference (stop_id PK, stop_name, lat, lon)
[dim] dim_weather: Daily weather (service_date_mst PK, precip_bin, snow_day, tmin_c, tmax_c, snow_mm)
[dim] dim_date: Calendar dimension (service_date_mst PK, day_name, is_weekend, season)
[agg] agg_reliability_by_route_day: Daily route performance → JOIN dim_route ON route_id, JOIN dim_weather ON service_date_mst | measures: pct_on_time, mean_delay_sec, p90_delay_sec, n_events
[agg] agg_reliability_by_stop_hour: Stop-hour performance → JOIN dim_stop ON stop_id | measures: pct_on_time, headway_adherence_rate, obs_headway_sec_p50, obs_headway_sec_p90
[agg] agg_weather_impacts_by_route: Weather effect on routes → JOIN dim_route ON route_id | measures: delta_pct_on_time, pct_on_time_normal
[mart] mart_stop_safety: Stop crash exposure → JOIN dim_stop ON stop_id | scores: crash_score_0_100, crash_250m_cnt, severe_250m_cnt
[mart] mart_stop_access: Stop sidewalk access → JOIN dim_stop ON stop_id | scores: access_score_0_100
[mart] mart_stop_equity: Stop demographic vulnerability → JOIN dim_stop ON stop_id | scores: vuln_score_0_100, pct_poverty_w
[mart] mart_stop_priority: Composite stop scoring → JOIN dim_stop ON stop_id | scores: priority_score, priority_rank
```

LLM system prompt addition:
> "Dimension tables (prefix `dim_`) are the **only** source for entity attributes like `stop_name`, `lat`, `lon`, `route_name`. Always JOIN `dim_stop ON stop_id` or `dim_route ON route_id`; never select these attributes from aggregate or mart tables."

---

## 17. Implementation Phases

### Pre-work — Add `feed_ts_utc` to `int_rt_events_resolved`
Add `feed_ts_utc` to the `base` CTE SELECT (already reading from `stg_rt_events`). Additive, no downstream breakage.

**File:** `dbt/models/intermediate/int_rt_events_resolved.sql`

### Phase 1 — Dimension Layer (additive, zero breakage)

**New files:**
- `dbt/models/dimensions/dim_stop.sql`
- `dbt/models/dimensions/dim_route.sql`
- `dbt/models/dimensions/dim_date.sql`
- `dbt/models/dimensions/dim_weather.sql` (from `stg_weather`, not `int_weather_by_date`)
- `dbt/models/dimensions/dim_census_tract.sql`
- `dbt/models/dimensions/schema.yml`
- `dbt_project.yml` — add `dimensions:` block with `schema: stg_denver`, `dim_date_start`/`dim_date_end_offset_days` vars
- `src/whyline/sync/constants.py` — introduce `MartEntry` + `MART_REGISTRY`

**Registry scope in Phase 1:** `constants.py` gains `MartEntry`, `MART_REGISTRY`, and `MART_BY_NAME` only. The derived API-facing constants (`GUARDRAIL_MARTS`, `PROMPT_MARTS`, `DOWNLOAD_MARTS`, `EXPORT_MARTS`, `SYNC_MARTS`, `HOT_MARTS`, `LATEST_RUN_DATE_ONLY`, `PARTITIONED_MARTS`) are NOT added to `constants.py` yet. The old `ALLOWLISTED_MARTS` tuple remains a **hardcoded list of the 9 current mart names** — it is NOT yet derived from the registry.

This means the API layer (`deps.py`, `llm.py`, `sql_guardrails.py`), sync/export code (`export_bq_marts.py`, `refresh_duckdb.py`), and all tests continue to import the same `ALLOWLISTED_MARTS` they use today. No runtime behavior changes in Phase 1. The registry is inert — it exists for inspection and invariant testing only.

The API layer and sync/export layer switch to registry-derived constants simultaneously in Phase 5.

**Acceptance criteria:**
- All 5 dim models build in BigQuery (in `stg_denver` dataset)
- `dim_stop` row count matches `mart_gtfs_stops` exactly
- `dim_weather` has `tmin_c`, `tmax_c`, `tavg_c` (verify these are absent from `int_weather_by_date`)
- `make test` passes (28 tests) — API layer unchanged, still using old constants

### Phase 2 — Fact Layer

**Pre-step:** Run uniqueness check on candidate grain `(feed_ts_utc, trip_id, stop_id)` against live `stg_rt_events` data in BigQuery to confirm before writing `unique_key` config.

**New files:**
- `dbt/models/facts/fct_transit_events.sql`
- `dbt/models/facts/fct_headway_adherence.sql`
- `dbt/models/facts/schema.yml` (uniqueness tests; conditional FK for nullable `stop_id`)
- `dbt_project.yml` — add `facts:` block with `schema: stg_denver`

**Acceptance criteria:**
- `fct_transit_events` row count within 0.1% of `stg_rt_events` for same date range
- Uniqueness test passes on confirmed grain
- FK test on `stop_id → dim_stop` passes with `where: "stop_id is not null"` filter

### Phase 3 — Aggregate Layer

**New files:**
- `dbt/models/aggregates/agg_reliability_by_route_day.sql`
- `dbt/models/aggregates/agg_reliability_by_stop_hour.sql`
- `dbt/models/aggregates/agg_weather_impacts_by_route.sql`
- `dbt/models/aggregates/schema.yml` (relationship meta, FK docs)
- `dbt_project.yml` — add `aggregates:` block with `schema: mart_denver`

**Metric parity check:** Snapshot `pct_on_time` and `mean_delay_sec` per route from `mart_reliability_by_route_day` over 30 days. Diff against `agg_reliability_by_route_day`. Must be ≤1%.

### Phase 4 — Mart Restructure + Compat Views

**Step 4.0 — Snapshot priority scores BEFORE any changes:**
```sql
SELECT stop_id, priority_score, priority_rank
FROM mart_priority_hotspots
ORDER BY priority_rank;
```
Save to a reference file. This is the baseline for parity checks.

**Step 4a — Build new mart models** (new file names; no conflict with old ones):
- `dbt/models/marts/mart_stop_reliability_score.sql`
- `dbt/models/marts/mart_stop_safety.sql`
- `dbt/models/marts/mart_stop_access.sql`
- `dbt/models/marts/mart_stop_equity.sql`
- `dbt/models/marts/mart_stop_priority.sql` (weights via `var()`)
- `dbt/models/marts/schema.yml` — relationship meta for all new models
- `dbt_project.yml` — add `priority_weight_*` vars

**Step 4b — Overwrite old mart files in-place** with explicit-column compat views (see Section 14). Same file paths, same names; dbt sees them as the same model — no collision:
```sql
-- dbt/models/marts/mart_reliability_by_route_day.sql (overwritten)
{{ config(materialized='view') }}
SELECT
    route_id, service_date_mst, precip_bin, snow_day,
    n_events, n_reported_events, pct_on_time,
    mean_delay_sec, median_delay_sec, p90_delay_sec, build_run_at
FROM {{ ref('agg_reliability_by_route_day') }}
```

**Acceptance criteria:**
- `mart_stop_priority.priority_score` within 0.5% of Phase 4.0 snapshot for top-100 stops (weights unchanged)
- `dbt run --vars '{priority_weight_safety: 0.4, priority_weight_equity: 0.4, priority_weight_reliability: 0.2}'` produces valid scores
- Old mart names still queryable in BigQuery via compat views

### Phase 5 — Python Backend + LLM + Frontend

**Files modified:**
- `src/whyline/sync/constants.py` — **add** the derived constants block (`GUARDRAIL_MARTS`, `PROMPT_MARTS`, `DOWNLOAD_MARTS`, `EXPORT_MARTS`, `SYNC_MARTS`, `HOT_MARTS`, `LATEST_RUN_DATE_ONLY`, `PARTITIONED_MARTS`) and replace the hardcoded `ALLOWLISTED_MARTS` tuple with `ALLOWLISTED_MARTS = GUARDRAIL_MARTS`. This is the registry cutover; all import sites flip simultaneously.
- `src/whyline/semantics/dbt_artifacts.py` — `prompt_models()`, `sql_models()`, `download_models()`; read `meta.layer` and `meta.relationships`
- `src/whyline/llm.py` — `_qualify_bigquery_tables` uses `model.fq_name` and receives `sql_models()` (not `prompt_models()`); layer-aware `build_schema_brief()` uses `prompt_models()`; update `PREBUILT_QUERIES` SQL to new table names
- `src/whyline/sql_guardrails.py` — allowlist from `GUARDRAIL_MARTS` (includes deprecated)
- `api/models.py` — add `layer` field to `ModelInfo`; add `DownloadOption` model
- `api/routers/downloads.py` — add `GET /api/downloads/options`; `POST /api/downloads/mart` validates against `DOWNLOAD_MARTS`
- `api/routers/models.py` — `GET /api/models` handler explicitly calls `dbt.prompt_models()` (NOT `allowed_models()` or `sql_models()`)
- `api/routers/filters.py` — query `dim_route` and `dim_stop`
- `api/deps.py` — `get_stop_lookup()` / `get_route_lookup()` from `dim_stop`, `dim_route`; startup handler for `STRICT_MODEL_VALIDATION`; **no generic `get_models()` — each call site uses the specific map it needs**
- `frontend/src/types/api.ts` — add `layer` to `ModelInfo`; add `DownloadOption` interface
- `frontend/src/components/ui/DownloadPanel.tsx` — fetch from `/api/downloads/options`
- `tests/semantics/test_dbt_artifacts.py` — update expected model names
- `tests/llm/test_llm.py` — update SQL fixtures and `ModelInfo` fixtures

**Acceptance criteria:**
- `/api/models` returns entries with `layer` field; no deprecated entries visible
- `/api/downloads/options` returns non-deprecated downloadable marts with labels
- LLM SQL for "which routes are least reliable?" uses `agg_reliability_by_route_day JOIN dim_route`
- Old mart names accepted by guardrails (deprecated `allow_sql=True`)
- Old mart names absent from schema brief (deprecated `allow_prompt=False`)
- `make test` passes
- Deploy with `STRICT_MODEL_VALIDATION=1` in Cloud Run `api-service` env vars; startup must succeed (all `allow_prompt`/`allow_sql` models present in manifest)

### Phase 6 — Sync & DuckDB

**Files modified:**
- `src/whyline/sync/export_bq_marts.py` — delete `PARTITIONED_MARTS` frozenset (line 23); per-mart dataset lookup; geom exclusion; iterate `EXPORT_MARTS` (never `ALLOWLISTED_MARTS`)
- `src/whyline/sync/refresh_duckdb.py` — `HOT_MARTS`, `LATEST_RUN_DATE_ONLY` from registry; iterate `SYNC_MARTS`; add `DEPRECATED_DUCKDB_ALIASES` views (Section 11)

**Acceptance criteria:**
- `make sync-duckdb` completes without error
- DuckDB contains `dim_stop`, `dim_route`, `dim_weather`, `agg_*`, `mart_stop_*`
- DuckDB also contains deprecated alias views (e.g. `mart_reliability_by_route_day`)
- Old cached SQL `SELECT route_id FROM mart_reliability_by_route_day` executes on DuckDB

### Phase 7 — Makefile + Exposures

**Files modified:**
- `Makefile` — update selectors (see Section 15)
- `dbt/models/exposures.yml` — update `depends_on` to new model names; fix description

### Phase 8 — Compat View Cleanup (after prod rebuild)

**Important:** Deleting dbt model files does NOT drop the corresponding BigQuery relations. Must explicitly drop them.

After all phases pass in production, the warehouse is rebuilt, and all prebuilt queries are updated:

1. **Drop BigQuery compat views** — run in BigQuery console or via `bq query`:
   ```sql
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_gtfs_stops`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_gtfs_routes`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_reliability_by_route_day`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_reliability_by_stop_hour`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_weather_impacts`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_crash_proximity_by_stop`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_access_score_by_stop`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_vulnerability_by_stop`;
   DROP VIEW IF EXISTS `{project}.{BQ_DATASET_MART}.mart_priority_hotspots`;
   ```
2. Delete 9 compat view `.sql` files from `dbt/models/marts/`
3. Delete deprecated `MartEntry` rows from `MART_REGISTRY`
4. Delete deprecated DuckDB alias dict and loop from `refresh_duckdb.py`
5. `dbt run --select aggregates marts` → no broken refs
6. `make test` passes

---

## 18. Critical Files Summary

| File | What changes | Phase |
|------|-------------|-------|
| `dbt/models/intermediate/int_rt_events_resolved.sql` | Add `feed_ts_utc` | Pre-work |
| `dbt/models/dimensions/dim_*.sql` (5 files) | New | 1 |
| `dbt/models/dimensions/schema.yml` | New | 1 |
| `dbt/models/facts/fct_transit_events.sql` | New | 2 |
| `dbt/models/facts/fct_headway_adherence.sql` | New | 2 |
| `dbt/models/facts/schema.yml` | New (conditional FK, uniqueness tests) | 2 |
| `dbt/models/aggregates/agg_*.sql` (3 files) | New | 3 |
| `dbt/models/aggregates/schema.yml` | New (relationship meta) | 3 |
| `dbt/models/marts/mart_stop_*.sql` (5 new files) | New | 4a |
| `dbt/models/marts/mart_*.sql` (9 old files) | Overwritten with explicit-column compat views | 4b |
| `dbt/models/marts/schema.yml` | Updated with relationship meta | 4 |
| `dbt/models/exposures.yml` | New model name refs, fix description | 7 |
| `dbt_project.yml` | Layer configs, date range vars, priority weight vars | 1–4 |
| `src/whyline/sync/constants.py` | `MartEntry` + `MART_REGISTRY` + derived sets | 1 |
| `src/whyline/llm.py:192–208` | `fq_name`-based BQ qualification; layer-aware brief | 5 |
| `src/whyline/semantics/dbt_artifacts.py` | 3 model maps; remove `allow_in_app` filter; missing-model skip (Phases 1–4) / `validate_registry_completeness()` fail-loud (Phase 5); `layer` + `relationships` fields | 5 |
| `src/whyline/engines/bigquery_engine.py:26-27` | `_allowed_models()` → `.sql_models()` | 5 |
| `src/whyline/sync/export_bq_marts.py:23,50` | Per-table dataset; geom exclusion; registry-driven | 6 |
| `src/whyline/sync/refresh_duckdb.py` | Registry-driven sets; deprecated DuckDB alias views | 6 |
| `api/models.py` | `layer` field in `ModelInfo`; `DownloadOption` model | 5 |
| `api/routers/downloads.py` | `GET /api/downloads/options` | 5 |
| `api/routers/filters.py` | Query `dim_route`, `dim_stop` | 5 |
| `api/deps.py` | `dim_stop`/`dim_route` lookups; `get_sql_models()` | 5 |
| `frontend/src/types/api.ts` | `layer` field; `DownloadOption` interface | 5 |
| `frontend/src/components/ui/DownloadPanel.tsx:8` | Fetch options from API | 5 |
| `Makefile` lines 155, 222, 234 | Updated dbt selectors; new layer targets | 7 |
| `tests/semantics/test_dbt_artifacts.py:25-33` | Updated expected model names | 5 |
| `tests/llm/test_llm.py:8-28` | Updated SQL and `ModelInfo` fixtures | 5 |
| `tests/test_registry.py` | New: registry invariant tests (5 rules from Section 7) | 1 |

---

## 19. Verification Plan

1. Pre-work: `dbt run --select int_rt_events_resolved` → `feed_ts_utc` column present in output
2. Phase 1: `dbt test --select dimensions` → all pass; `dim_stop` row count = `mart_gtfs_stops`; `dim_weather` has `tmin_c`
3. Phase 2: uniqueness BQ query confirms grain; `dbt test --select facts` passes; conditional FK test passes
4. Phase 3: metric parity check `agg_reliability_by_route_day` vs `mart_reliability_by_route_day` ≤1% delta on 30-day sample
5. Phase 4: `mart_stop_priority` within 0.5% of Phase 4.0 snapshot for top-100 stops
6. Phase 4: old mart names queryable in BigQuery via compat views with correct column sets
7. `dbt test` → all tests pass across all layers
8. `make sync-duckdb` → DuckDB contains dim + agg + mart + deprecated alias views
9. Old cached SQL `SELECT route_id FROM mart_reliability_by_route_day WHERE service_date_mst >= ...` executes correctly on DuckDB
10. `make api-dev`:
    - `GET /api/models` → `layer` field present; no deprecated entries
    - `GET /api/downloads/options` → labelled mart list; no deprecated entries
    - `POST /api/sql/generate` → SQL uses `agg_reliability_by_route_day` and JOINs `dim_route ON route_id`
    - `POST /api/query/run` → stop_name enriched from `dim_stop`; both engines work
    - `POST /api/downloads/mart` → CSV download works for `agg_reliability_by_route_day`
11. `make test` → all 28 pytest tests pass
12. Frontend: download dropdown populated from API (not static list); prebuilt queries run; map renders
