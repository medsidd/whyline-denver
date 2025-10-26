# WhyLine Denver – Pipeline Architecture

**Last Updated**: October 25, 2025

This document describes the complete data pipeline architecture for WhyLine Denver, from source APIs through transformation to final consumption. It covers design decisions, integration points, scalability considerations, and guidance for extending the system.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architectural Principles](#architectural-principles)
3. [Medallion Architecture (Bronze → Silver → Gold)](#medallion-architecture-bronze--silver--gold)
4. [Component Deep Dive](#component-deep-dive)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Integration Points](#integration-points)
7. [Design Decisions & Rationale](#design-decisions--rationale)
8. [Scalability & Performance](#scalability--performance)
9. [Disaster Recovery & Data Integrity](#disaster-recovery--data-integrity)
10. [Future Enhancements](#future-enhancements)
11. [Adaptation Guide (For Other Cities)](#adaptation-guide-for-other-cities)
12. [Additional Resources](#additional-resources)

---

## System Overview

WhyLine Denver is a **dual-engine transit analytics platform** built on modern cloud-native principles. It ingests public data from 7 sources, transforms them through a governed dbt pipeline, and serves curated datasets through both BigQuery (cloud warehouse) and DuckDB (local analytics engine).

### Key Characteristics

| Attribute | Value |
|-----------|-------|
| **Architecture Pattern** | Medallion (Bronze → Silver → Gold) + Dual-Engine Analytics |
| **Primary Warehouse** | Google BigQuery (serverless, columnar) |
| **Local Engine** | DuckDB (embedded, file-backed) |
| **Orchestration** | GitHub Actions (cron workflows) |
| **Transformation** | dbt 1.8 (SQL + Jinja templating) |
| **Ingestion** | Python 3.11 CLIs (click framework) |
| **Storage** | Google Cloud Storage (object storage) |
| **App Layer** | Streamlit 1.37 (interactive Python dashboard) |
| **Annual Cost** | ~$25 (storage + compute) |
| **Data Latency** | 2 minutes (GTFS-RT), 24 hours (static data), 3-7 days (weather) |
| **Data Volume** | ~20GB raw, ~5GB marts, ~144M GTFS-RT events/year |

### Tech Stack

```
┌─ PRESENTATION ────┐
│ Streamlit App     │ ← Natural language queries (Gemini LLM)
│ CSV Exports       │ ← Downloadable datasets
│ dbt Docs (Pages)  │ ← Auto-generated data catalog
└───────────────────┘
         ↕ SQL queries
┌─ ANALYTICS ENGINES ─────────────────┐
│ BigQuery (prod)   │ DuckDB (local) │
│ • Serverless      │ • File-backed  │
│ • Geospatial      │ • Free         │
│ • 1TB/mo free     │ • Fast         │
└──────────────────────────────────────┘
         ↕ dbt models
┌─ TRANSFORMATION ──────────────────────┐
│ dbt (29 models)                       │
│ • Staging (11): dedupe, normalize    │
│ • Intermediate (7): derived metrics  │
│ • Marts (7): analytical tables       │
│ • Tests (40+): data quality          │
└───────────────────────────────────────┘
         ↕ ingestion → loading
┌─ ORCHESTRATION ────────────────────────┐
│ GitHub Actions (6 workflows)          │
│ • Hourly: GTFS-RT (15x/day)          │
│ • Nightly: Static data (1x/day)      │
│ • Nightly: dbt build + test          │
│ • CI: Lint + test on PR              │
└────────────────────────────────────────┘
         ↕ HTTP APIs
┌─ DATA SOURCES (Public APIs) ───────────┐
│ • RTD GTFS/GTFS-RT                    │
│ • Denver Open Data (crashes, sidewalks)|
│ • NOAA/NCEI (weather)                 │
│ • U.S. Census (ACS, TIGER/Line)       │
└────────────────────────────────────────┘
```

---

## Architectural Principles

WhyLine Denver was designed with these principles:

### 1. **Separation of Concerns**
- **Ingestion**: Python CLIs fetch raw data, no transformation logic
- **Storage**: GCS holds immutable raw files with partition-friendly paths
- **Loading**: Parametric loader adds metadata, handles idempotency
- **Transformation**: dbt owns all business logic (no SQL in Python)
- **Consumption**: App queries curated marts only (guardrails prevent raw table access)

### 2. **Idempotency & Replayability**
- Every ingestion output includes MD5 hash; loader skips duplicates
- Raw tables are append-only with `_ingested_at` timestamps
- Staging models deduplicate by ranking (`rank = 1` on latest `_extract_date`)
- dbt incremental models use `WHERE date > MAX(date) - INTERVAL 35 DAY` for safe replays

### 3. **Cost Optimization**
- GitHub Actions stays within free tier (2,000 min/month; we use ~800)
- BigQuery scans ~100GB/month (well under 1TB free tier)
- GCS storage is $0.55/year (16GB GTFS-RT compressed)
- DuckDB enables free local analytics (no cloud costs for development)

### 4. **Data Quality as Code**
- 40+ dbt tests enforce uniqueness, referential integrity, value ranges
- QA script validates freshness, row counts, cross-platform consistency
- Pre-commit hooks prevent secrets, large files, trailing whitespace
- CI blocks merges if lint/tests fail

### 5. **Governed Access**
- LLM-to-SQL limited to SELECT-only queries
- Only allow-listed marts are queryable (no raw tables)
- BigQuery `MAX_BYTES_BILLED` caps costs (default 2GB per query)
- Dry-run preview shows estimated bytes before execution

### 6. **Dual-Engine Flexibility**
- BigQuery for production-scale analysis (geospatial, large aggregations)
- DuckDB for local development, demos, offline work
- Parquet export layer ensures portability between engines
- Same SQL works on both (with minor dialect adjustments)

---

## Medallion Architecture (Bronze → Silver → Gold)

WhyLine Denver implements a **three-tier medallion architecture** inspired by Databricks' lakehouse patterns:

### Bronze Layer (Raw Zone)

**Purpose**: Store immutable, unprocessed data exactly as received from source APIs.

**Storage**: Google Cloud Storage (`gs://whylinedenver-raw/raw/`)

**Partitioning**: `raw/<dataset>/extract_date=YYYY-MM-DD/<files>`

**Examples**:
- `raw/rtd_gtfs/extract_date=2025-10-24/gtfs/routes.txt`
- `raw/rtd_gtfsrt/snapshot_at=2025-10-24T12:00/trip_updates.csv.gz`
- `raw/noaa_daily/extract_date=2025-10-24/weather.csv.gz`

**Loading to BigQuery**:
- Parametric loader (`load/bq_load.py`) reads registry (`load/registry.py`)
- Each job spec defines: glob pattern, target table, partitioning, clustering
- Adds metadata columns: `_ingested_at`, `_source_path`, `_extract_date`, `_hash_md5`
- Tracks loaded files in `__ingestion_log` (idempotency via MD5)

**Key Properties**:
- **Immutable**: Files never modified after upload
- **Append-only**: Raw tables grow without updates
- **Auditable**: `_source_path` and `_hash_md5` enable traceability
- **Schema-on-read**: BigQuery infers schema from CSV headers

---

### Silver Layer (Refined Zone)

**Purpose**: Clean, deduplicate, and standardize raw data into reusable building blocks.

**Storage**: BigQuery `stg_denver` dataset (views + some tables)

**Model Types**:
1. **Staging Models (`stg_*`)**: Deduplicate, create geometry, normalize enums
2. **Intermediate Models (`int_*`)**: Compute complex derived metrics (headways, delays)

**Transformations**:
- **Deduplication**: Window functions rank by `_ingested_at DESC`, filter `rank = 1`
- **Geometry**: `ST_GEOGPOINT(lon, lat)` for spatial joins
- **Timezone**: Convert UTC → MST for local analysis
- **Coalescing**: Merge arrival/departure delays into single metric
- **Enrichment**: Join static GTFS to realtime events

**Example Flow**:
```sql
-- Raw table (Bronze)
raw_gtfs_routes: 1,000 rows (multiple extracts, duplicates)

-- Staging model (Silver)
stg_gtfs_routes:
  SELECT DISTINCT ON (route_id)
    route_id, route_short_name, route_long_name, ...
  FROM raw_gtfs_routes
  ORDER BY route_id, _extract_date DESC
→ 50 unique routes (deduplicated)
```

**Key Properties**:
- **Mostly views**: Lightweight, always reflect latest raw data
- **No business logic**: Just cleaning and structuring
- **Testable**: Uniqueness, not-null, referential integrity tests
- **Reusable**: Staging models feed multiple marts

---

### Gold Layer (Consumption Zone)

**Purpose**: Domain-specific analytical tables optimized for querying and visualization.

**Storage**: BigQuery `mart_denver` dataset (tables, incremental where appropriate)

**Domains**:
1. **Reliability**: On-time performance, weather impacts
2. **Safety**: Crash proximity to transit stops
3. **Equity**: Vulnerability scores for transit-dependent populations
4. **Access**: Pedestrian infrastructure quality

**Materialization**:
- **Incremental tables** (reliability marts): Partition by date, rebuild last 35 days
- **Full-refresh tables** (safety, equity, access): Rebuild nightly (smaller datasets)

**Optimization**:
- **Partitioning**: `service_date_mst` for date-range queries
- **Clustering**: `route_id`, `stop_id` for join performance
- **Aggregation**: Pre-compute metrics (no raw event queries in app)

**Export**:
- Selected marts exported as Parquet to GCS (`marts/<mart_name>/run_date=YYYY-MM-DD/`)
- DuckDB syncs from Parquet (hot marts materialized, cold marts as views)

**Key Properties**:
- **Curated**: Only intentional, documented tables
- **Tested**: Data quality enforced via dbt tests
- **Performant**: Aggregated to human-scale granularity
- **Documented**: dbt docs auto-generate catalog

---

## Component Deep Dive

### Ingestion Layer

**Location**: `src/whylinedenver/ingest/`

**Architecture**: Click-based Python CLIs with common utilities

#### Ingestion Modules

| Module | Frequency | Output Size | API | Notes |
|--------|-----------|-------------|-----|-------|
| `gtfs_static.py` | Monthly | ~1-2MB | RTD GTFS ZIP | 6 TXT files extracted |
| `gtfs_realtime.py` | Hourly (15x/day) | ~500KB trip updates, ~50KB positions per snapshot | RTD GTFS-RT Protobuf | 3 snapshots, 2 min apart |
| `noaa_daily.py` | Nightly | ~10KB per day | NOAA CDO JSON | Rolling 30-day backfill |
| `denver_crashes.py` | Nightly | ~5MB (5 years) | ArcGIS REST | Paginated, 1000 records/page |
| `denver_sidewalks.py` | Nightly | ~2MB | ArcGIS REST | ~35K segments with geometry |
| `acs.py` | Annual | ~50KB | Census API | 2023 ACS 5-year, tract-level |
| `denver_tracts.py` | Annual | ~500KB | TIGERweb GeoJSON | ~140 tracts with polygons |

#### Common Utilities (`ingest/common.py`)

```python
def http_get_with_retry(url, headers=None, timeout=30, retries=3):
    """Exponential backoff retry logic"""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
            else:
                raise

def write_csv(df, path, gcs_bucket=None, compress=True):
    """Write CSV to local or GCS with optional gzip"""
    if compress:
        path += '.gz'
    if gcs_bucket:
        client = storage.Client()
        bucket = client.bucket(gcs_bucket)
        blob = bucket.blob(path)
        blob.upload_from_string(df.to_csv(index=False), content_type='text/csv')
    else:
        df.to_csv(path, index=False, compression='gzip' if compress else None)

def write_manifest(path, metadata, gcs_bucket=None):
    """Write JSON manifest with row counts, MD5, schema_version"""
    manifest = {
        'extract_date': metadata['extract_date'],
        'row_count': metadata['row_count'],
        'hash_md5': metadata['hash_md5'],
        'schema_version': 'v1',
        'source_url': metadata.get('source_url'),
    }
    # Write to GCS or local
    ...
```

#### Ingestion Workflow

```
1. HTTP GET with retry logic
2. Parse response (JSON, Protobuf, or ZIP extraction)
3. Transform to pandas DataFrame
4. Validate schema (required columns present)
5. Write CSV to GCS/local (with partition path)
6. Write manifest JSON (metadata)
7. Log success with row count
```

---

### Loading Layer

**Location**: `load/bq_load.py`, `load/registry.py`

**Architecture**: Parametric BigQuery loader driven by job registry

#### Job Registry (`load/registry.py`)

```python
LOAD_JOBS = [
    {
        'name': 'gtfs_rt_trip_updates',
        'pattern': 'rtd_gtfsrt/snapshot_at=*/trip_updates.csv.gz',
        'table': 'raw_gtfsrt_trip_updates',
        'partition': 'feed_ts_utc',
        'clustering': ['trip_id', 'route_id'],
    },
    # ... 12 more jobs
]
```

#### Loader Logic (`bq_load.py`)

```python
def load_job(job_spec, bucket, since=None):
    # 1. List files matching glob pattern in GCS
    files = list_gcs_files(bucket, job_spec['pattern'], since)

    # 2. For each file:
    for file in files:
        # 2a. Check if already loaded (query __ingestion_log)
        if is_loaded(file['md5']):
            continue

        # 2b. Load to BigQuery via COPY command
        load_csv_to_bq(
            uri=f'gs://{bucket}/{file["path"]}',
            table=job_spec['table'],
            partition_field=job_spec.get('partition'),
            cluster_fields=job_spec.get('clustering'),
        )

        # 2c. Record in __ingestion_log
        insert_log_entry(file['path'], file['md5'], table=job_spec['table'])
```

**Why Parametric?** Adding a new data source requires only:
1. Create ingestion module
2. Add job spec to registry
3. No code changes to loader

---

### Transformation Layer (dbt)

**Location**: `dbt/models/`

**Architecture**: Layered SQL models with tests and documentation

#### dbt Project Structure

```
dbt/
├── dbt_project.yml           # Project config (name, version, model paths)
├── profiles/
│   └── profiles.yml          # BigQuery connection config
├── models/
│   ├── sources_raw.yml       # 13 raw table definitions + freshness checks
│   ├── staging/              # 11 models (views)
│   │   ├── gtfs/             # GTFS static staging
│   │   ├── realtime/         # GTFS-RT staging
│   │   ├── weather/          # Weather staging
│   │   ├── crashes/          # Crash staging
│   │   ├── sidewalks/        # Sidewalk staging
│   │   └── census/           # Census staging
│   ├── intermediate/         # 7 models (views)
│   │   └── *.sql             # Derived metrics (headways, delays)
│   └── marts/                # 7 models (tables/incremental)
│       ├── reliability/      # 3 models
│       ├── safety/           # 1 model
│       ├── equity/           # 2 models
│       └── access/           # 1 model
├── macros/
│   ├── make_point.sql        # ST_GEOGPOINT helper
│   ├── to_mst_date.sql       # UTC → MST timezone conversion
│   └── ...                   # 10+ macros
└── tests/
    └── *.sql                 # Custom data tests
```

#### Key Macros

```sql
-- macros/make_point.sql
{% macro make_point(lon, lat) %}
  ST_GEOGPOINT({{ lon }}, {{ lat }})
{% endmacro %}

-- macros/to_mst_date.sql
{% macro to_mst_date(ts_utc) %}
  DATE({{ ts_utc }}, 'America/Denver')
{% endmacro %}

-- macros/to_mst_hour.sql
{% macro to_mst_hour(ts_utc) %}
  EXTRACT(HOUR FROM DATETIME({{ ts_utc }}, 'America/Denver'))
{% endmacro %}
```

#### Incremental Model Pattern

```sql
-- models/marts/reliability/mart_reliability_by_route_day.sql
{{
  config(
    materialized='incremental',
    partition_by={'field': 'service_date_mst', 'data_type': 'date'},
    cluster_by=['route_id'],
  )
}}

SELECT
  route_id,
  service_date_mst,
  precip_bin,
  COUNT(*) AS n_events,
  AVG(CASE WHEN is_on_time THEN 1.0 ELSE 0.0 END) AS pct_on_time,
  ...
FROM {{ ref('int_rt_events_resolved') }}
LEFT JOIN {{ ref('int_weather_by_date') }} USING (service_date_mst)

{% if is_incremental() %}
  WHERE service_date_mst > (
    SELECT MAX(service_date_mst) - INTERVAL 35 DAY FROM {{ this }}
  )
{% endif %}

GROUP BY route_id, service_date_mst, precip_bin
```

**Why 35-day lookback?** Ensures late-arriving data (delayed snapshots, NOAA backfills) gets incorporated without full rebuild.

---

### Sync Layer (BigQuery ↔ DuckDB)

**Location**: `src/whylinedenver/sync/`

**Architecture**: Two-stage process (export → refresh)

#### Export Stage (`sync/export_bq_marts.py`)

```python
def export_mart(mart_name, run_date):
    # 1. Query BigQuery mart
    df = bq_client.query(f'SELECT * FROM mart_denver.{mart_name}').to_dataframe()

    # 2. Write to GCS as Parquet
    path = f'marts/{mart_name}/run_date={run_date}/*.parquet'
    df.to_parquet(f'gs://{bucket}/{path}', engine='pyarrow', compression='snappy')

    # 3. Update export state (last_export.json)
    metadata = {
        'run_date': run_date,
        'row_count': len(df),
        'exported_at': datetime.utcnow().isoformat(),
    }
    upload_json(f'gs://{bucket}/marts/{mart_name}/last_export.json', metadata)

    # 4. Record in BigQuery state table
    insert_export_log(mart_name, run_date, len(df))
```

#### Refresh Stage (`sync/refresh_duckdb.py`)

```python
def refresh_duckdb(duckdb_path='data/warehouse.duckdb'):
    conn = duckdb.connect(duckdb_path)

    # 1. For each mart, read last_export.json from GCS
    for mart in MART_NAMES:
        metadata = download_json(f'gs://{bucket}/marts/{mart}/last_export.json')
        run_date = metadata['run_date']

        # 2. Download Parquet files to local cache
        parquet_path = download_parquet(
            f'gs://{bucket}/marts/{mart}/run_date={run_date}/*.parquet',
            local_cache='data/marts_cache/'
        )

        # 3. Materialize or view in DuckDB
        if mart in HOT_MARTS:
            # Hot marts: fully materialized tables
            conn.execute(f'DROP TABLE IF EXISTS {mart}')
            conn.execute(f'CREATE TABLE {mart} AS SELECT * FROM read_parquet("{parquet_path}")')
        else:
            # Cold marts: views over Parquet files
            conn.execute(f'CREATE OR REPLACE VIEW {mart} AS SELECT * FROM read_parquet("{parquet_path}")')

        # 4. Update local sync state
        update_sync_state(mart, run_date, metadata['row_count'])
```

**Hot Marts** (materialized): `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`
**Cold Marts** (views): All safety, equity, access marts

**Why differentiate?** Hot marts are queried frequently in app (need fast response); cold marts are referenced less often (view over Parquet is acceptable).

---

## Data Flow Diagrams

### End-to-End Pipeline

```
┌─────────────┐
│ Source APIs │
└──────┬──────┘
       │ HTTP GET (Python CLIs)
       ↓
┌────────────────────┐
│ GCS (Bronze Layer) │  ← Immutable CSVs, partitioned paths
│ raw/*              │
└─────────┬──────────┘
          │ BigQuery COPY
          ↓
┌──────────────────────┐
│ BigQuery Raw Tables  │  ← Append-only, metadata columns
│ raw_* (13 tables)    │
└─────────┬────────────┘
          │ dbt staging models
          ↓
┌─────────────────────────┐
│ BigQuery Staging Views  │  ← Deduplicated, normalized
│ stg_* (11 views)        │
└─────────┬───────────────┘
          │ dbt intermediate models
          ↓
┌────────────────────────────┐
│ BigQuery Intermediate Views│  ← Derived metrics
│ int_* (7 views)            │
└─────────┬──────────────────┘
          │ dbt mart models
          ↓
┌──────────────────────┐
│ BigQuery Mart Tables │  ← Domain-specific, optimized
│ mart_* (7 tables)    │
└─────────┬────────────┘
          │ Parquet export to GCS
          ↓
┌─────────────────────┐
│ GCS (Parquet Files) │  ← marts/*/run_date=YYYY-MM-DD/*.parquet
└─────────┬───────────┘
          │ DuckDB sync
          ↓
┌────────────────────┐
│ DuckDB Warehouse   │  ← Local file (data/warehouse.duckdb)
│ mart_* (7 tables)  │
└─────────┬──────────┘
          │ SQL queries
          ↓
┌────────────────────┐
│ Streamlit App      │  ← Natural language interface
│ • Charts           │
│ • Maps             │
│ • CSV exports      │
└────────────────────┘
```

### GTFS-RT Hourly Cycle (Detailed)

```
12:00 UTC (5am MST)
  ↓
┌─ GitHub Actions: hourly-gtfs-rt.yml ─┐
│                                        │
│ [Minute 0] Snapshot 1                 │
│   RTD API: /TripUpdate.pb → CSV       │
│   RTD API: /VehiclePosition.pb → CSV  │
│   Upload to GCS                        │
│                                        │
│ [Minute 2] Snapshot 2 (repeat)        │
│                                        │
│ [Minute 4] Snapshot 3 (repeat)        │
│                                        │
│ Workflow exits (~5 min total)         │
└────────────────────────────────────────┘
  ↓
GCS: gs://whylinedenver-raw/raw/rtd_gtfsrt/snapshot_at=2025-10-24T12:00/
  ├─ trip_updates.csv.gz (500KB, 5-10K rows)
  └─ vehicle_positions.csv.gz (50KB, 400-500 rows)

12:30 UTC (5:30am MST) [+30 min offset]
  ↓
┌─ GitHub Actions: hourly-bq-load.yml ──┐
│                                        │
│ Scan GCS for new files since 12:00    │
│ Load trip_updates → raw_gtfsrt_trip... │
│ Load vehicle_positions → raw_gtfsrt... │
│ Record MD5 in __ingestion_log          │
│                                        │
│ Workflow exits (~2 min)                │
└────────────────────────────────────────┘
  ↓
BigQuery: raw_gtfsrt_trip_updates (partitioned by feed_ts_utc)
  New rows appended with _ingested_at = 2025-10-24T12:32:00Z

... Process repeats 14 more times through 7pm MST (02:00 UTC)
```

---

## Integration Points

### External APIs

| API | Endpoint | Auth | Rate Limit | Reliability |
|-----|----------|------|------------|-------------|
| **RTD GTFS Static** | https://www.rtd-denver.com/files/gtfs/google_transit.zip | None | Unlimited | 99.9% uptime |
| **RTD GTFS-RT** | https://www.rtd-denver.com/files/gtfs-rt/TripUpdate.pb | None | Unlimited | 98% (occasional 503s) |
| **Denver Open Data (ArcGIS)** | https://services1.arcgis.com/.../FeatureServer/{layer} | None | 60 req/min | 95% (sometimes slow) |
| **NOAA CDO** | https://www.ncei.noaa.gov/cdo-web/api/v2/data | Token required | 1000 req/day | 99% |
| **Census API** | https://api.census.gov/data/{year}/acs/acs5 | Optional key | 500 req/day (no key), unlimited (with key) | 99.5% |

**Failure Handling**:
- HTTP retries with exponential backoff (3 attempts, 1.5x factor)
- Fallback to local CSV for NOAA if API fails
- Workflows continue even if one ingestor fails (logged, not fatal)

### Cloud Services

| Service | Usage | Configuration |
|---------|-------|---------------|
| **Google Cloud Storage** | Raw file storage (bronze layer) | Bucket: `whylinedenver-raw`, Location: us-central1 |
| **BigQuery** | Data warehouse (silver + gold layers) | Project: `whyline-denver`, Datasets: `raw_denver`, `stg_denver`, `mart_denver` |
| **GitHub Actions** | Orchestration | 2,000 free minutes/month (using ~800) |
| **Hugging Face Spaces** (planned) | Streamlit app hosting | Free tier (CPU, 16GB storage) |

### Authentication

```
┌─ Local Development ─────────────────┐
│ gcloud auth application-default     │
│   login                             │
│ → Stores token in ~/.config/gcloud/│
│ → Python libraries auto-discover    │
└─────────────────────────────────────┘

┌─ GitHub Actions ────────────────────┐
│ secrets.GCP_SA_KEY (base64 JSON)   │
│ → Decoded to /tmp/gcp-key.json     │
│ → GOOGLE_APPLICATION_CREDENTIALS    │
│   env var points to temp file      │
└─────────────────────────────────────┘
```

---

## Design Decisions & Rationale

### Why BigQuery?

**Alternatives Considered**: Snowflake, Redshift, PostgreSQL, DuckDB-only

**Decision**: BigQuery

**Rationale**:
- **Serverless**: No cluster management, auto-scales
- **Cost**: 1TB/month free tier (WhyLine Denver scans ~100GB/month)
- **Geospatial**: Native `GEOGRAPHY` type for spatial joins (critical for crash proximity, vulnerability)
- **Integration**: Works seamlessly with dbt, Looker, Data Studio
- **Performance**: Columnar storage, parallelized queries

**Trade-offs**:
- ❌ Vendor lock-in (mitigated by Parquet exports)
- ❌ Query cost beyond free tier (mitigated by guardrails)

---

### Why DuckDB?

**Alternatives Considered**: SQLite, PostgreSQL, BigQuery-only

**Decision**: DuckDB as secondary engine

**Rationale**:
- **Free**: No cloud costs for development/demos
- **Fast**: Columnar, vectorized execution (10-100x faster than SQLite)
- **Parquet-native**: Queries Parquet files directly (no import needed)
- **Portable**: Single `.duckdb` file, easy to distribute
- **SQL Compatibility**: Most BigQuery SQL works as-is

**Trade-offs**:
- ❌ Limited concurrency (file locking; not suitable for multi-user production)
- ❌ No geospatial functions (marts pre-compute spatial metrics in BigQuery)

---

### Why GitHub Actions?

**Alternatives Considered**: Airflow, Prefect, Dagster, AWS Step Functions

**Decision**: GitHub Actions

**Rationale**:
- **Free**: 2,000 minutes/month for private repos (WhyLine Denver uses ~800)
- **Zero Ops**: No servers, no databases, no maintenance
- **Version-controlled**: Workflows are YAML in repo; changes are auditable
- **Simple**: Cron syntax, no DAG complexity
- **Integrated**: Same platform as code, PRs, CI

**Trade-offs**:
- ❌ Limited observability (no UI for re-running individual tasks)
- ❌ Cron jitter (5-15 min delay during peak times; acceptable for WhyLine Denver)
- ❌ No complex dependencies (can't express "run task B only if task A succeeds"; we use time offsets instead)

**When to Migrate**: If hourly snapshots need sub-minute precision or complex error handling, consider Airflow/Prefect.

---

### Why Medallion Architecture?

**Alternatives Considered**: Star schema, OBT (One Big Table), Lambda architecture

**Decision**: Medallion (Bronze → Silver → Gold)

**Rationale**:
- **Separation of Concerns**: Raw vs. cleaned vs. analytical data
- **Auditability**: Bronze layer preserves source-of-truth
- **Reusability**: Silver layer (staging) feeds multiple marts
- **Incremental Improvement**: Can refine gold layer without re-ingesting bronze

**Trade-offs**:
- ❌ More layers = more complexity (mitigated by dbt's DAG management)

---

## Scalability & Performance

### Current Bottlenecks

| Component | Current Limit | Observed Load | Headroom |
|-----------|---------------|---------------|----------|
| **GTFS-RT API** | ~1000 req/min | 45 req/day (3 per hour × 15 hours) | 30,000x |
| **BigQuery Slots** | Auto-scaling | ~10 queries/day | Virtually unlimited |
| **GCS Bandwidth** | 5 Gbps egress | ~50 MB/day uploads | 10,000x |
| **GitHub Actions** | 2,000 min/month | ~800 min/month | 2.5x |
| **dbt Build Time** | ~12 min (nightly-bq) | Acceptable | N/A |

**Most Constrained**: GitHub Actions compute minutes (closest to free tier limit).

**Mitigation**: If usage grows beyond 2,000 min/month, either:
1. Switch to self-hosted runners (free compute, but ops burden)
2. Reduce hourly snapshot frequency (e.g., every 2 hours instead of hourly)
3. Pay for additional GitHub Actions minutes (~$0.008/min)

---

### Scaling Scenarios

#### Scenario 1: 10x Data Volume (1.44B GTFS-RT events/year)

**Impact**:
- GCS storage: $5.50/year (still negligible)
- BigQuery storage: $5/year (still cheap)
- dbt build time: ~30 min (incremental models help)
- DuckDB sync: ~20 min (Parquet compression keeps size manageable)

**Recommendation**: No architecture changes needed; just monitor costs.

---

#### Scenario 2: Add 5 More Cities

**Impact**:
- Ingestion: 5x CLIs (straightforward; just update GTFS URLs)
- BigQuery datasets: Separate datasets per city (e.g., `raw_chicago`, `stg_chicago`, `mart_chicago`)
- dbt models: Multi-city support via variables (`{{ var('city') }}`)
- DuckDB: Separate `.duckdb` files per city

**Recommendation**: Introduce `city` dimension in tables; use dbt variables to template models.

---

#### Scenario 3: Real-time App Queries (100 users, 1000 queries/day)

**Current**: App queries DuckDB locally (single-user)

**Problem**: DuckDB file locking prevents concurrent queries

**Solution**:
1. **Option A**: Deploy app with BigQuery backend (serverless, auto-scales)
   - Cost: ~$1/day for 1000 queries (scanning ~100GB)
   - Latency: ~2-5 seconds per query
2. **Option B**: Deploy DuckDB as read-only service (e.g., via DuckDB WASM in browser)
   - Cost: Free (compute on client-side)
   - Latency: <1 second
3. **Option C**: Use Snowflake/Databricks with free tier

**Recommendation**: Option A (BigQuery) for <$30/month operational cost.

---

## Disaster Recovery & Data Integrity

### Backup Strategy

| Layer | Backup Location | Retention | Recovery Time |
|-------|-----------------|-----------|---------------|
| **Bronze (GCS)** | Same bucket, versioning enabled | 30 days | Instant (read older version) |
| **Silver/Gold (BigQuery)** | BigQuery time-travel | 7 days | Minutes (restore via `FOR SYSTEM_TIME AS OF`) |
| **dbt Code** | GitHub (version control) | Infinite | Seconds (git checkout) |
| **DuckDB** | Rebuilds nightly from Parquet | N/A (ephemeral) | 20 minutes (re-run sync) |

### Data Validation

#### Level 1: Ingestion Validation

```python
# In common.py
def validate_schema(df, required_columns):
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(f'Missing columns: {missing}')

    if len(df) == 0:
        raise ValueError('Empty DataFrame')
```

#### Level 2: dbt Tests

- **Uniqueness**: `unique(route_id)` → Fails if duplicates exist
- **Referential Integrity**: `relationships(route_id → stg_gtfs_routes)` → Fails if orphaned foreign keys
- **Value Ranges**: `accepted_range(pct_on_time: [0, 1])` → Fails if values outside bounds

#### Level 3: QA Script

- Validates freshness (GTFS-RT <2 hours, weather <7 days)
- Validates row counts (40+ snapshots/day)
- Validates cross-platform consistency (BigQuery vs. DuckDB mart counts within 5%)

### Failure Recovery Procedures

#### Scenario: Hourly GTFS-RT workflow fails (503 from RTD API)

**Detection**: Status badge turns red; QA script shows <40 snapshots/day

**Recovery**:
1. Check RTD API status (external issue?)
2. If transient, wait for next hourly run (auto-retry)
3. If persistent, manually trigger workflow: `gh workflow run hourly-gtfs-rt.yml`

**Prevention**: Already implemented (3-snapshot redundancy per hour)

---

#### Scenario: dbt test fails (uniqueness violation in stg_gtfs_routes)

**Detection**: nightly-bq workflow fails; email alert (if configured)

**Recovery**:
1. Identify failing test: `dbt test --select stg_gtfs_routes`
2. Investigate duplicates:
   ```sql
   SELECT route_id, COUNT(*) FROM stg_denver.stg_gtfs_routes GROUP BY 1 HAVING COUNT(*) > 1;
   ```
3. Fix deduplication logic in model
4. Re-run: `dbt run --select stg_gtfs_routes`
5. Re-test: `dbt test --select stg_gtfs_routes`

**Prevention**: Add regression test to catch this pattern

---

#### Scenario: BigQuery table accidentally deleted

**Recovery**:
1. Use BigQuery time-travel (up to 7 days):
   ```sql
   CREATE TABLE mart_denver.mart_reliability_by_route_day AS
   SELECT * FROM mart_denver.mart_reliability_by_route_day
   FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR);
   ```
2. If >7 days old, rebuild from GCS bronze layer:
   ```bash
   make bq-load  # Reload raw tables
   make nightly-bq  # Rebuild marts
   ```

**Prevention**: Enable deletion protection on critical tables (future enhancement)

---

## Future Enhancements

### Phase 1: UX Polish (In Progress)

- [ ] Prebuilt question buttons (e.g., "Which routes are most delayed during snow?")
- [ ] Richer filters (date ranges, route picker, stop search)
- [ ] Charts (heatmaps, small multiples)
- [ ] Hotspot map (Pydeck layers for vulnerability + crashes)
- [ ] CSV export for all charts
- [ ] "Download full mart as CSV" flow (with safety caps)

### Phase 2: LLM Integration (In Progress)

- [ ] Gemini API wired via `LLM_API_KEY`
- [ ] Natural language → SQL translation
- [ ] Guardrails enforced (SELECT-only, allow-list, cost caps)

### Phase 3: Deployment & Hosting

- [ ] Streamlit app on Hugging Face Spaces (default DuckDB engine)
- [ ] Optional BigQuery engine via secrets
- [ ] Custom domain + Cloudflare TLS proxy
- [ ] Health check workflow + status badge

### Phase 4: Documentation & Discoverability

- [ ] Polished README (value prop, quickstart, prod path, FAQ)
- [ ] dbt docs published to GitHub Pages
- [ ] Architecture diagrams (pipelines + app/allow-list)
- [ ] Data attributions in app footer

### Phase 5: Advanced Analytics

- [ ] Predictive reliability models (GTFS-RT + weather → forecast delays)
- [ ] Route recommendation engine (given origin/destination + time, suggest best route)
- [ ] Equity scoring refinement (add disability, age, language barriers)
- [ ] Integration with Denver 311 data (correlate service requests with transit access)

### Phase 6: Multi-City Expansion

- [ ] Templatize dbt models with `{{ var('city') }}`
- [ ] Multi-dataset support (separate `raw_chicago`, `mart_chicago`, etc.)
- [ ] Unified app with city selector
- [ ] Cross-city benchmarking (compare Denver vs. Chicago reliability)

---

## Adaptation Guide (For Other Cities)

WhyLine Denver is designed to be extensible. Here's how to adapt it for your city:

### Step 1: Update Data Sources

| Component | What to Change | How |
|-----------|----------------|-----|
| **GTFS Static** | RTD URL → Your agency's GTFS ZIP | `src/whylinedenver/ingest/gtfs_static.py` line 15 |
| **GTFS-RT** | RTD APIs → Your agency's Trip Updates/Vehicle Positions | `src/whylinedenver/ingest/gtfs_realtime.py` lines 20-22 |
| **Crashes** | Denver ArcGIS → Your city's crash data | `src/whylinedenver/ingest/denver_crashes.py` line 25 |
| **Sidewalks** | Denver ArcGIS → Your city's sidewalk data | `src/whylinedenver/ingest/denver_sidewalks.py` line 30 |
| **Weather** | Denver station (USC00053005) → Your local station | `src/whylinedenver/ingest/noaa_daily.py` line 18 |
| **Census** | Denver County (FIPS 08031) → Your county | `src/whylinedenver/ingest/acs.py` line 40 |

### Step 2: Update Geography

| Component | What to Change | How |
|-----------|----------------|-----|
| **Bounding Box** | Denver bounds → Your city bounds | Update `MIN_LON`, `MAX_LON`, `MIN_LAT`, `MAX_LAT` constants |
| **Timezone** | America/Denver → Your timezone | Update `to_mst_date()` macro in `dbt/macros/` |
| **Census Tracts** | Denver tracts → Your tracts | `src/whylinedenver/ingest/denver_tracts.py` line 35 |

### Step 3: Test Ingestion

```bash
# Test each ingestor locally
python -m whylinedenver.ingest.gtfs_static --local
python -m whylinedenver.ingest.gtfs_realtime --local --snapshots 1
python -m whylinedenver.ingest.noaa_daily --local --start 2025-01-01 --end 2025-01-31
# ... etc
```

### Step 4: Update dbt Models (Optional)

Most dbt models are GTFS-standard and will work as-is. Exceptions:

- **Timezone macros**: Update `to_mst_date()` → `to_{your_tz}_date()`
- **Geography-specific models**: If your city has different spatial data (e.g., bike lanes instead of sidewalks), create new staging model

### Step 5: Deploy Workflows

Update GitHub Actions secrets:
- `GCP_PROJECT_ID` → Your project
- `GCS_BUCKET` → Your bucket
- Update cron schedules in `.github/workflows/` to match your city's service hours

### Step 6: Rebrand App

- Update `APP_BRAND_NAME` in `.env` (e.g., "WhyLine Chicago")
- Update attribution links in app footer
- Update README

---

## Additional Resources

- **[Interactive Model Lineage & Docs](https://medsidd.github.io/whyline-denver/)** – Explore dbt models, view full lineage graphs, and browse column-level documentation
- **[Root README](../README.md)** – Project overview, quickstart, FAQ
- **[dbt Models Documentation](../dbt/models/README.md)** – All 29 models, tests, materialization strategies
- **[GitHub Workflows Documentation](../.github/workflows/README.md)** – Orchestration details
- **[QA Validation Guide](QA_Validation_Guide.md)** – Health checks and troubleshooting
- **[Data Contracts](contracts/CONTRACTS.md)** – Schema specifications

---

**Questions?** Open an issue or check the workflow logs in GitHub Actions. For data quality issues, run `./scripts/qa_script.sh`.
