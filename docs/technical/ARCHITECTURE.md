# Architecture

WhyLine Denver is a Python/SQL transit warehouse served by FastAPI and a Next.js dashboard. This is the canonical architecture reference; [operations](OPERATIONS.md) records dated deployment state and cost observations.

## Processing and serving

```text
16 ingestion CLIs, including the continuous GTFS-RT poller on a VM
  → GCS raw files and manifests (the poller also archives every feed payload)
  → BigQuery raw_denver (explicit schemas + loader metadata)
  → dbt stg_denver (silver: source-conformed staging)
  → dbt core_denver (gold core: Kimball dimensions, facts, bridges)
  → dbt mart_denver (gold serving: 35 marts; 20 app marts, 2 live views)
  → GCS Parquet exports of the 20 app marts → DuckDB warehouse

BigQuery → FastAPI → Next.js /app   (the API also answers on DuckDB; the dashboard uses BigQuery)
```

| Boundary | Implementation and reason |
|---|---|
| Source ingestion | `src/whyline/ingest/`: 16 standalone argparse CLIs (see [data pipeline](DATA_PIPELINE.md#ingestion)), shared retry/I/O utilities, local or GCS output. Raw snapshots preserve source lineage. The continuous GTFS-RT poller (`gtfs_rt_stream`) is a long-running VM process: it derives stop visits itself and archives every feed payload. |
| Loading | `load/bq_load.py` and `registry.py`: explicit ordered schemas, metadata, MD5-based skipping. Raw CSVs are normalized extracts, not universally untouched source records. |
| Transformation | Medallion layers: 25 silver staging models, 33 gold-core models (eight dimensions, 21 facts, four bridges: Type 2 GTFS dimensions with surrogate keys and Unknown members; incremental schedule, stop-visit and trip-status facts; nightly crash, weather, demographics and other facts), and 35 serving marts built only from gold core. Three legacy models are disabled since the stop-visit cutover. See the [model reference](../../dbt/models/README.md). |
| Published schema | `DbtArtifacts` reads manifest/catalog. Models must have `config.meta.allow_in_app` and be in `sync/constants.py`: the 20 `ALLOWLISTED_MARTS` or the 2 `LIVE_MARTS` (live views, BigQuery only). |
| Export | The 20 app marts: date-partitioned marts by rebuilt partition (selected using `build_run_at` as well as date checkpoints), the rest as daily snapshots. Live views and `allow_in_app: false` marts are not exported. |
| Embedded warehouse | `sync/refresh_duckdb.py` materializes the 20 app marts. Partitioned history is limited by `DUCKDB_MAX_AGE_DAYS` (90 by default); snapshots use latest run date. |
| HTTP | Five routers in `api/routers/` (health, filters including `/routes/shapes`, sql, query, downloads), registered under `/api`; request/response models in `api/models.py`. |
| Presentation | Next.js 14, React 18, Zustand, TanStack Query, Recharts, Deck.gl/MapLibre, CodeMirror. |

## Why two engines?

BigQuery performs cloud transformations and answers every dashboard query (the dashboard sends `engine: bigquery`); the live views exist only there. Its API query engine uses a dry-run estimate and `MAX_BYTES_BILLED` (2,000,000,000 by default). That cap applies to this engine's queries, not every loader/dbt/export/billing query in the project.

DuckDB serves a copied warehouse of the 20 app marts without per-query BigQuery analysis charges, for API callers that ask for it and for the warehouse download. Local querying needs no cloud credentials when the warehouse, dbt artifacts, and sync-state configuration are local. Downloading data, hosting it on Cloud Run, refreshing it, or accessing GCS still has infrastructure/access costs.

`llm.adapt_sql_for_engine()` handles the supported dialect rewrites and BigQuery table qualification. It is not a general SQL transpiler; test queries on each intended engine.

## Query boundary

Generation sends the user's question, filters, and schema brief to the configured LLM. Gemini is implemented; stub mode returns canned queries. OpenAI and Anthropic provider names raise `NotImplementedError`.

Generation, validation, and execution apply `sanitize_sql()`. It checks SELECT/WITH shape, single-statement syntax, denylisted write keywords, allowed table references and BigQuery namespaces. It adds `LIMIT 5000` only when there is no numeric limit. Existing limits are preserved. The query response displays at most 10,000 rows after execution; a display limit is not a scan limit.

The guardrails are regex-based checks, not a database permission system. Keep cloud identities least-privileged and retain server-side validation regardless of browser validation. See [API reference](API_REFERENCE.md).

## State and caching

- Prompt and query caches are process-local and expire according to `src/whyline/logs.py`; restarting clears them. They are not durable shared caches.
- dbt schema loading is lazy and cached with `lru_cache`, not validated by `/api/health`.
- Stop/route enrichment lookups are cached after successful reads from DuckDB (stops also have a local GTFS fallback).
- DuckDB connections are thread-local and read-only by default. With `DUCKDB_COPY_LOCAL=1`, each source version is copied to `warehouse-<mtime_ns>-<size>.duckdb` beside `DUCKDB_LOCAL_PATH`. One shared check reads the source at most once a minute, and each thread reopens on a newer copy. Results can trail a refresh by that minute, the mount's metadata cache and the 180-second query cache. With `DUCKDB_COPY_LOCAL=0`, connections keep the warehouse they opened. Verify actual results after a refresh.
- The browser persists selected dashboard fields in localStorage, but not result data or validation state. This survives closing a tab; it does not implement synchronized cross-tab state.
- Query logs contain hashes and execution metadata. Engine logs can include SQL snippets. The frontend mounts Vercel Analytics and Speed Insights. See [FAQ](../public/FAQ.md) before making privacy claims.

## Hosting and orchestration

The API runs as Cloud Run service `whylinedenver-api`. The Makefile deployment defaults are 0–3 instances, 2 vCPU, and 2 GiB; verify live configuration separately. The GCS bucket is mounted at `/mnt/gcs`, and DuckDB is copied locally for reliable access.

The continuous GTFS-RT poller runs as a container on the `rt-stream-poller` VM (image set in the instance's `image-uri` metadata; see [operations](OPERATIONS.md) for upgrade steps). It reads both feeds every 15 seconds, times each stop visit itself, and publishes 15-minute batches. Two Cloud Run jobs share an image and dispatch on `JOB_TYPE`: `realtime-load` runs every 15 minutes (it loads the poller's batches, snapshots service alerts and Veo vehicles, and builds `fct_stop_visit` and `fct_trip_status`); `realtime-ingest`, the old 15-minute snapshot collector, is paused. Three independent GitHub Actions cron workflows ingest static sources, transform/export, and refresh DuckDB. The two realtime GitHub workflows are manual alternatives, not scheduled collectors. CI runs Python lint/tests and deploys dbt docs on successful pushes to `main`.

Next.js uses server-side rewrites from `/api/*` to `API_BASE_URL`. This avoids requiring the browser to call a separate origin; it is not an authentication boundary and does not make the public API secret. `StopMap` must use `ssr: false` because MapLibre needs browser APIs.

## Design lessons

Preserving raw files and loader metadata makes replay and lineage possible. Materializing expensive schedule expansion avoids recomputing it through multiple views. Incremental processing and partition predicates reduce repeated work, but lookback windows also determine which late corrections can be applied. Export checkpoints must account for revised older data.

These tradeoffs and failures are retained in [cost optimization](../case-studies/bigquery-cost-optimization-2025.md) and [pipeline recovery](../case-studies/pipeline-recovery-2026.md). Current spend belongs in [operations](OPERATIONS.md), not architecture estimates.
