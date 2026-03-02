# Architecture

This document describes WhyLine Denver's system design, component relationships, and the reasoning behind key technical decisions.

---

## System Overview

WhyLine Denver is a full-stack transit analytics platform with five major components:

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                      │
│                                                                  │
│  External APIs → Ingestors → GCS (raw)                          │
│                                   ↓                             │
│  BigQuery raw_denver ← bq_load.py                               │
│        ↓                                                         │
│  BigQuery stg_denver + mart_denver  ← dbt                       │
│        ↓                                                         │
│  GCS Parquet marts  ← export_bq_marts.py                        │
│        ↓                                                         │
│  DuckDB warehouse.duckdb  ← refresh_duckdb.py                   │
└─────────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────────┐
│  API LAYER                                                       │
│                                                                  │
│  FastAPI (api/)                                                  │
│    /api/health          liveness + freshness                     │
│    /api/filters         sidebar options from marts               │
│    /api/sql             LLM generation + validation              │
│    /api/query           execute SQL on BigQuery or DuckDB        │
│    /api/downloads       CSV + warehouse exports                  │
└─────────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND LAYER                                                  │
│                                                                  │
│  Next.js 14 dashboard (frontend/)                               │
│    Step 1: Natural language question → LLM SQL generation        │
│    Step 2: Review and edit SQL in CodeMirror editor              │
│    Step 3: Execute, view table + auto-detected charts + map      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Medallion Data Architecture

Data moves through three progressive refinement layers:

### Bronze — Raw ingestion (`raw_denver` dataset)

Immutable copies of source data. Nothing is transformed here — raw values, original field names, original timezones. Tables are partitioned by `extract_date`.

Every file loaded into BigQuery is tracked in `raw_denver.__ingestion_log` with its MD5 hash. The loader skips files whose MD5 already appears in the log, making all loads idempotent.

### Silver — Staging and intermediate (`stg_denver` dataset)

Two sub-layers:

**Staging** (10 dbt views): Clean, rename, deduplicate. Build geometry columns. Parse GTFS time strings. All staging models are views — no storage cost, always reflects the latest raw data.

Exception: `stg_rt_events` is an incremental table. The raw GTFS-RT source is large enough that viewing it as a plain view would scan the full table on every downstream model run.

**Intermediate** (6 dbt models): Derive metrics from staging. Expand the GTFS schedule into individual stop arrivals (`int_scheduled_arrivals`). Match realtime events to the schedule (`int_rt_events_resolved`). Calculate headway intervals. Aggregate weather by date.

`int_scheduled_arrivals` is a materialized table (~22M rows) because expanding the GTFS calendar is expensive and the output is needed by multiple downstream models. Pre-materializing it once per day avoids redundant computation.

### Gold — Marts (`mart_denver` dataset)

Analytics-ready tables with business logic applied and spatial joins pre-computed. Seven marts covering four domains: reliability, safety, equity, and access. All marts are allow-listed in the API (`meta.allow_in_app: true` in dbt schema.yml) so they can be queried by name.

---

## Dual-Engine Pattern

Every query endpoint accepts an `engine` parameter: `"duckdb"` or `"bigquery"`.

### BigQuery

- **When**: Production analytics, large historical queries, queries requiring up-to-the-minute data
- **Cost**: Charged per byte scanned, capped at 2 GB per query (`MAX_BYTES_BILLED`)
- **Auth**: GCP service account via `GOOGLE_APPLICATION_CREDENTIALS`
- **Tables**: Fully-qualified names (`project.dataset.table`)
- **Freshness**: Live — reflects the last dbt run (typically within ~1 hour of 9 AM UTC)

### DuckDB

- **When**: Local development, free exploration, offline use, CI tests
- **Cost**: Zero compute cost — runs locally or from GCS-mounted file
- **Auth**: None
- **Tables**: Unqualified names — DuckDB uses the warehouse file
- **Freshness**: Reflects the last DuckDB sync (typically within ~30 min of 9:30 AM UTC)

### SQL dialect adaptation

The same SQL must work on both engines. The API adapts SQL automatically via `adapt_sql_for_engine()` in `src/whyline/llm.py`:

- **DuckDB**: Replaces BigQuery-style `DATE_SUB(col, INTERVAL N DAY)` with DuckDB `col - INTERVAL 'N' DAY`
- **BigQuery**: Qualifies unqualified table names to their fully-qualified `project.dataset.table` form

CTEs are detected and skipped — only FROM/JOIN table references are qualified.

---

## FastAPI Service

`api/` is a thin HTTP wrapper over the `whyline` Python package. It uses FastAPI with five routers registered under `/api`.

**Dependency injection** (`api/deps.py`): dbt artifacts (manifest.json + catalog.json) are loaded once at process startup using Python's `@lru_cache`. This makes schema information available to all endpoints without repeated disk reads. The same pattern is used for the stop and route lookup DataFrames used to enrich query results.

**Two-layer caching**:
1. `prompt_cache`: Keyed by (LLM provider, engine, question, filters). Avoids calling the LLM again for identical questions.
2. `query_cache`: Keyed by (engine, sanitized SQL). Avoids re-executing identical queries within a session.

**SQL guardrails** (`src/whyline/sql_guardrails.py`): Every SQL string — whether generated by the LLM or pasted by the user — is sanitized before execution:
- Must be a single SELECT statement (no semicolons inside, no non-SELECT statements)
- Denylist: INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, MERGE, TRUNCATE, GRANT, REVOKE, PRAGMA
- Table names must be from the dbt allowlist (models with `meta.allow_in_app: true`)
- BigQuery: project and dataset must match allowed values from config
- LIMIT 5000 is appended if no LIMIT clause is present

---

## LLM Integration

The LLM converts natural language questions into SQL. Key design decisions:

**Schema context, not data**: The LLM receives only a schema brief (model name, description, first 7 column names), not actual data. This keeps prompts small and avoids sending user data to the LLM provider.

**Deterministic guardrails after generation**: The LLM output goes through `sanitize_sql()` regardless of quality. The LLM is not trusted to produce safe SQL; the guardrail layer enforces safety.

**Provider abstraction**: `call_provider()` in `src/whyline/llm.py` dispatches to the active provider. Production uses Gemini (`gemini-2.5-flash`). Development uses a stub provider that returns pre-written SQL for known patterns. Switching providers is a one-line env var change (`LLM_PROVIDER`).

**Prompt caching**: Identical (provider, engine, question, filters) tuples return the cached SQL without calling the LLM. This reduces both cost and latency.

---

## Frontend Architecture

`frontend/` is a Next.js 14 App Router application.

**State management**: All dashboard state lives in a single Zustand store (`dashboardStore.ts`) with localStorage persistence. This means state survives page refreshes and is shared across browser tabs. The store is the single source of truth for: selected engine, active filters, the question, generated/edited SQL, validation status, and query results.

**API communication**: The Next.js server rewrites all `/api/*` requests to `${API_BASE_URL}/api/*` (configured in `next.config.mjs`). This means the FastAPI URL is never exposed to the browser and there are no CORS issues.

**Visualization**: Charts are auto-detected from the result column names by `detectChartType()` in `src/lib/chartLogic.ts`. The map (`StopMap`) is shown when `lat` and `lon` columns are present. All visualization components are client-side; `StopMap` uses dynamic import with `ssr: false` because maplibre-gl requires browser APIs.

---

## Infrastructure

### Compute

| Service | Purpose | Configuration |
|---------|---------|---------------|
| Cloud Run service (`whylinedenver-api`) | FastAPI REST API | 0–3 instances, 2 vCPU, 2 Gi memory |
| Cloud Run jobs (`realtime-ingest`, `realtime-load`) | Every-5-min GTFS-RT capture and load | Triggered by Cloud Scheduler |
| GitHub Actions | Nightly batch pipelines (ingest, dbt, DuckDB sync) | 3 scheduled workflows |
| Vercel | Next.js frontend hosting | Auto-deploys on push to main |

### Storage

| Resource | Contents |
|---------|---------|
| GCS `whylinedenver-raw/raw/` | Raw ingest outputs, partitioned by extract_date |
| GCS `whylinedenver-raw/marts/` | Parquet exports from BigQuery |
| GCS `whylinedenver-raw/marts/duckdb/` | DuckDB warehouse file |
| GCS `whylinedenver-raw/state/` | `sync_state.json` tracking freshness |
| BigQuery `raw_denver` | Raw ingested tables (13 tables) |
| BigQuery `stg_denver` | Staging + intermediate dbt models |
| BigQuery `mart_denver` | Final mart tables (queried by API) |
| Artifact Registry | Docker images for API service and realtime jobs |

### GCS-Fuse on Cloud Run

The DuckDB warehouse on Cloud Run is GCS-Fuse mounted at `/mnt/gcs`. On first query, the DuckDB engine copies the file to `/tmp/warehouse.duckdb` for faster performance (controlled by `DUCKDB_COPY_LOCAL=1`). Thread-local DuckDB connections ensure thread safety under Cloud Run's concurrent request handling.

---

## Key Design Decisions

**Why dbt for transformations?**
SQL-first transformations are version-controlled, testable, and self-documenting. dbt's incremental materializations handle the cost of re-running on large GTFS-RT data without a full scan. The dbt manifest.json also serves as the authoritative schema source for the API's allowlist and prompt context.

**Why DuckDB alongside BigQuery?**
BigQuery is excellent for production scale but requires GCP credentials and charges per byte. DuckDB enables free local development, offline use, CI testing without cloud access, and easy data sharing (one file download). The dual-engine pattern makes both first-class citizens.

**Why Cloud Run Jobs for realtime, not Cloud Functions?**
Cloud Run Jobs support longer execution times (up to 24 hours), have better cost predictability, and can be updated by pushing a new container image. The 5-minute trigger from Cloud Scheduler is well-suited to this model.

**Why Next.js server-side API rewrites?**
The FastAPI URL is an internal implementation detail. Routing `/api/*` through Next.js means the URL can change without frontend changes, avoids CORS configuration, and keeps the API key out of the browser.

**Why Zustand over React Query or Redux?**
The dashboard has a sequential, multi-step state machine (question → SQL → results). Zustand's synchronous actions and localStorage persistence fit this pattern well. React Query is used for the filter options endpoint (a pure server-state fetch), while Zustand handles the multi-step workflow state.

---

## Cost Optimization History

The platform has been aggressively optimized. Key wins:

1. **MD5-based BigQuery deduplication**: Eliminated repeated loads of identical files. Removed ~126,000 redundant queries/day.
2. **Incremental dbt models**: `stg_rt_events` and reliability marts use incremental materialization with explicit partition filters, dramatically reducing bytes scanned per run.
3. **`int_scheduled_arrivals` pre-materialization**: Pre-expanding the GTFS calendar once (vs in every downstream view) eliminated repeated full-table joins on stop_times.
4. **Cloud Run job frequency reduction**: Reduced from every 5 min to every 5 min with a more efficient dbt realtime subset (`dbt-run-realtime`).

See [docs/COST_OPTIMIZATION_DEC_2025.md](../COST_OPTIMIZATION_DEC_2025.md) for the detailed analysis.
