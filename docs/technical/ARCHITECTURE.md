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

BigQuery mart_denver → FastAPI → Next.js /app
```

| Boundary | Implementation and reason |
|---|---|
| Source ingestion | `src/whyline/ingest/`: 16 standalone argparse CLIs (see [data pipeline](DATA_PIPELINE.md#ingestion)), shared retry/I/O utilities, local or GCS output. Raw snapshots preserve source lineage. The continuous GTFS-RT poller (`gtfs_rt_stream`) is a long-running VM process: it derives stop visits itself and archives every feed payload. |
| Loading | `load/bq_load.py` and `registry.py`: explicit ordered schemas, metadata, MD5-based skipping. Raw CSVs are normalized extracts, not universally untouched source records. |
| Transformation | Medallion layers: 25 silver staging models, 33 gold-core models (eight dimensions, 21 facts, four bridges: Type 2 GTFS dimensions with surrogate keys and Unknown members; incremental schedule, stop-visit and trip-status facts; nightly crash, weather, demographics and other facts), and 35 serving marts built only from gold core. Three legacy models are disabled since the stop-visit cutover. See the [model reference](../../dbt/models/README.md). |
| Published schema | `DbtArtifacts` reads manifest/catalog. Models must have `config.meta.allow_in_app` and be in `sync/constants.py`: the 20 `ALLOWLISTED_MARTS` or the 2 `LIVE_MARTS` (live views). |
| HTTP | Five routers in `api/routers/` (health, filters including `/routes/shapes`, sql, query, downloads), registered under `/api`; request/response models in `api/models.py`. |
| Presentation | Next.js 15, React 19, Zustand, TanStack Query, Recharts, Deck.gl/MapLibre, CodeMirror. |

## One engine

Every query runs on BigQuery: the dashboard's, the API's and the downloads'. Visitor SQL gets a dry run first (an estimate, plus BigQuery's own statement and table check), then runs with `MAX_BYTES_BILLED` (2,000,000,000 by default) and a 120-second job timeout. That cap applies to the API's queries, not to loader, dbt or billing queries.

Until November 19, 2026 the nightly build also exported the 20 app marts to Parquet and copied them into a DuckDB file that the API could query and serve as a download. Nothing read that path but direct API callers, it lagged BigQuery by up to a day, and it needed its own checks, so it was removed (see [operations](OPERATIONS.md)). The tests still run dbt models on small inputs in DuckDB; that's a test harness, not part of the app.

`llm.qualify_tables()` writes bare mart names as `project.mart_denver.table` (CTEs and qualified names stay). It does not translate SQL dialects.

## Query boundary

Generation sends the user's question, filters, and schema brief to the configured LLM. Gemini is implemented; stub mode returns canned queries. OpenAI and Anthropic provider names raise `NotImplementedError`.

Generation, validation, and execution apply `sanitize_sql()`. It checks SELECT/WITH shape, single-statement syntax, denylisted write keywords, allowed table references and BigQuery namespaces. It adds `LIMIT 5000` only when there is no numeric limit. Existing limits are preserved in the SQL; the API fetches at most 10,000 rows for a query, and the scan is bounded separately (`MAX_BYTES_BILLED`, a 120-second job timeout).

`sanitize_sql()` is a text check for early, readable errors, not the security boundary: a comma join or a comment after `FROM` passes it. BigQuery's dry run therefore re-checks visitor SQL before it runs (statement type and the tables it reads). Least-privileged cloud identities are the third layer: the API account should read only `mart_denver`, with the live views authorized on the datasets they read (since November 19, 2026; replacing an authorized view needs owner rights on those datasets, see [deployment](DEPLOYMENT.md)) and retain server-side validation regardless of browser validation. See [API reference](API_REFERENCE.md).

## State and caching

- Prompt and query caches are process-local and expire according to `src/whyline/logs.py`; restarting clears them. They are not durable shared caches.
- dbt schema loading is lazy and cached with `lru_cache`, not validated by `/api/health`.
- Stop/route enrichment lookups (`mart_gtfs_stops`, `mart_gtfs_routes`) are read from BigQuery once per process and kept; a failed read is retried on the next query.
- The browser persists selected dashboard fields in localStorage, but not result data or validation state. This survives closing a tab; it does not implement synchronized cross-tab state.
- Query logs contain hashes and execution metadata. Engine logs can include SQL snippets. The frontend mounts Vercel Analytics and Speed Insights. See [FAQ](../public/FAQ.md) before making privacy claims.

## Hosting and orchestration

The API runs as Cloud Run service `whylinedenver-api`. The Makefile deployment defaults are 0–3 instances, 2 vCPU, and 2 GiB, with no storage mount; verify live configuration separately.

The continuous GTFS-RT poller runs as a container on the `rt-stream-poller` VM (image set in the instance's `image-uri` metadata; see [operations](OPERATIONS.md) for upgrade steps). It reads both feeds every 15 seconds, times each stop visit itself, and publishes 15-minute batches. Two Cloud Run jobs share an image and dispatch on `JOB_TYPE`: `realtime-load` runs every 15 minutes (it loads the poller's batches, snapshots service alerts and Veo vehicles, and builds `fct_stop_visit` and `fct_trip_status`); the old snapshot collector `realtime-ingest` was deleted in November 2026. Two chained GitHub Actions workflows ingest static sources (Nightly Ingest) and then build and test BigQuery (Nightly BigQuery). The realtime GitHub workflow is a manual alternative, not a scheduled collector. CI runs Python lint/tests and deploys dbt docs on successful pushes to `main`.

Next.js uses server-side rewrites from `/api/*` to `API_BASE_URL`. This avoids requiring the browser to call a separate origin; it is not an authentication boundary and does not make the public API secret. `StopMap` must use `ssr: false` because MapLibre needs browser APIs.

## Design lessons

Preserving raw files and loader metadata makes replay and lineage possible. Materializing expensive schedule expansion avoids recomputing it through multiple views. Incremental processing and partition predicates reduce repeated work, but lookback windows also determine which late corrections can be applied. Export checkpoints must account for revised older data.

These tradeoffs and failures are retained in [cost optimization](../case-studies/bigquery-cost-optimization-2025.md) and [pipeline recovery](../case-studies/pipeline-recovery-2026.md). Current spend belongs in [operations](OPERATIONS.md), not architecture estimates.
