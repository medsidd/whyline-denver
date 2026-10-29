# Architecture

WhyLine Denver is a Python/SQL transit warehouse served by FastAPI and a Next.js dashboard. This is the canonical architecture reference; [operations](OPERATIONS.md) records dated deployment state and cost observations.

## Processing and serving

```text
Seven public-source ingestors
  → GCS raw files and manifests
  → BigQuery raw_denver (explicit schemas + loader metadata)
  → dbt stg_denver (silver: source-conformed staging)
  → dbt core_denver (gold core: Kimball dimensions, facts, bridge)
  → dbt mart_denver (gold serving: nine marts)
  → GCS Parquet exports → DuckDB warehouse

BigQuery or DuckDB → FastAPI → Next.js /app
```

| Boundary | Implementation and reason |
|---|---|
| Source ingestion | `src/whyline/ingest/`: standalone argparse CLIs, shared retry/I/O utilities, local or GCS output. Raw snapshots preserve source lineage. The continuous GTFS-RT poller (`gtfs_rt_stream`) is a long-running VM process: it derives stop visits itself and archives every feed payload (built, not deployed). |
| Loading | `load/bq_load.py` and `registry.py`: explicit ordered schemas, metadata, MD5-based skipping. Raw CSVs are normalized extracts, not universally untouched source records. |
| Transformation | Medallion layers: 17 silver staging models (mostly views; `stg_rt_events` incremental), 15 gold-core models (Type 2 GTFS dimensions with surrogate keys and Unknown members; incremental trip-observation, schedule, stop-arrival, stop-visit and trip-status facts; nightly crash, weather, and demographics facts; a weighted stop-tract bridge), and nine serving marts built only from gold core. See the [model reference](../../dbt/models/README.md). |
| Published schema | `DbtArtifacts` reads manifest/catalog. Models must have `config.meta.allow_in_app` and be in `sync/constants.py::ALLOWLISTED_MARTS`. |
| Export | Two partitioned reliability marts; seven snapshot marts. Rebuilt partitions are selected using `build_run_at` as well as date checkpoints. |
| Embedded warehouse | `sync/refresh_duckdb.py` materializes nine marts. Partitioned history is limited by `DUCKDB_MAX_AGE_DAYS` (90 by default); snapshots use latest run date. |
| HTTP | Five routers in `api/routers/`, registered under `/api`; request/response models in `api/models.py`. |
| Presentation | Next.js 14, React 18, Zustand, TanStack Query, Recharts, Deck.gl/MapLibre, CodeMirror. |

## Why two engines?

BigQuery performs cloud transformations and supports querying the current mart tables. Its API query engine uses a dry-run estimate and `MAX_BYTES_BILLED` (2,000,000,000 by default). That cap applies to this engine's queries, not every loader/dbt/export/billing query in the project.

DuckDB serves a copied warehouse without per-query BigQuery analysis charges. Local querying needs no cloud credentials when the warehouse, dbt artifacts, and sync-state configuration are local. Downloading data, hosting it on Cloud Run, refreshing it, or accessing GCS still has infrastructure/access costs.

`llm.adapt_sql_for_engine()` handles the supported dialect rewrites and BigQuery table qualification. It is not a general SQL transpiler; test queries on each intended engine.

## Query boundary

Generation sends the user's question, filters, and schema brief to the configured LLM. Gemini is implemented; stub mode returns canned queries. OpenAI and Anthropic provider names raise `NotImplementedError`.

Generation, validation, and execution apply `sanitize_sql()`. It checks SELECT/WITH shape, single-statement syntax, denylisted write keywords, allowed table references and BigQuery namespaces. It adds `LIMIT 5000` only when there is no numeric limit. Existing limits are preserved. The query response displays at most 10,000 rows after execution; a display limit is not a scan limit.

The guardrails are regex-based checks, not a database permission system. Keep cloud identities least-privileged and retain server-side validation regardless of browser validation. See [API reference](API_REFERENCE.md).

## State and caching

- Prompt and query caches are process-local and expire according to `src/whyline/logs.py`; restarting clears them. They are not durable shared caches.
- dbt schema loading is lazy and cached with `lru_cache`, not validated by `/api/health`.
- Stop/route enrichment lookups are cached after successful reads from DuckDB (stops also have a local GTFS fallback).
- DuckDB connections are thread-local and read-only by default. With `DUCKDB_COPY_LOCAL=1`, the source is copied to a temporary local path when opening a connection. Existing connections can keep the old warehouse; verify actual results after a refresh.
- The browser persists selected dashboard fields in localStorage, but not result data or validation state. This survives closing a tab; it does not implement synchronized cross-tab state.
- Query logs contain hashes and execution metadata. Engine logs can include SQL snippets. The frontend mounts Vercel Analytics and Speed Insights. See [FAQ](../public/FAQ.md) before making privacy claims.

## Hosting and orchestration

The API runs as Cloud Run service `whylinedenver-api`. The Makefile deployment defaults are 0–3 instances, 2 vCPU, and 2 GiB; verify live configuration separately. The GCS bucket is mounted at `/mnt/gcs`, and DuckDB is copied locally for reliable access.

Two Cloud Run jobs share an image and dispatch on `JOB_TYPE`. Cloud Scheduler invokes them; the October 26 readback showed 15-minute capture/load schedules. Three independent GitHub Actions cron workflows ingest static sources, transform/export, and refresh DuckDB. The two realtime GitHub workflows are manual alternatives, not scheduled collectors. CI runs Python lint/tests and deploys dbt docs on successful pushes to `main`.

Next.js uses server-side rewrites from `/api/*` to `API_BASE_URL`. This avoids requiring the browser to call a separate origin; it is not an authentication boundary and does not make the public API secret. `StopMap` must use `ssr: false` because MapLibre needs browser APIs.

## Design lessons

Preserving raw files and loader metadata makes replay and lineage possible. Materializing expensive schedule expansion avoids recomputing it through multiple views. Incremental processing and partition predicates reduce repeated work, but lookback windows also determine which late corrections can be applied. Export checkpoints must account for revised older data.

These tradeoffs and failures are retained in [cost optimization](../case-studies/bigquery-cost-optimization-2025.md) and [pipeline recovery](../case-studies/pipeline-recovery-2026.md). Current spend belongs in [operations](OPERATIONS.md), not architecture estimates.
