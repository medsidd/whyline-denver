# Repository guidance

## Session startup

1. Invoke `task-observer` before task-oriented work that uses tools and produces deliverables.
2. When loading a skill, read OPEN observations tagged to it in this stable repository's `skill-observations/log.md` and apply active `cross-cutting-principles.md` guidance. Preserve concurrent entries.
3. Read [documentation index](docs/README.md), [operations](docs/technical/OPERATIONS.md), and relevant technical references before editing.
4. Inspect `git status` and preserve unrelated changes. Source code, Makefile recipes, and workflow definitions take precedence over older narrative descriptions.

## Scope and cloud actions

The August pause was superseded by an approved October 2026 restart. Realtime data comes from the stream poller on the `rt-stream-poller` VM and the `realtime-load` scheduler; `realtime-ingest` (the old snapshot capture) is intentionally paused, so don't resume it. See [operations](docs/technical/OPERATIONS.md) for dated health. Do not reapply the obsolete freeze or infer permission to change schedules from setup examples.

Keep BigQuery/GCS data intact. Read-only inspection is appropriate for status requests. Starting new paid runs, changing recurring schedules, deploying, publishing, deleting data, or changing credentials must be within the user's authorized scope. Existing authorization persists; do not repeatedly ask for the same action.

Never print or commit `.env`, credential files, token values, or inline service-account JSON. Avoid importing `whyline.config` merely to inspect defaults: it loads `.env` and may materialize credentials. `bq_load.py` creates cloud clients in `main()`, not on module import.

## Commands and limits

Run from the repository root with `.venv` activated. `make install` installs root requirements and pre-commit; also install `api/requirements.txt` for FastAPI.

| Command | Actual behavior |
|---|---|
| `make test` | Offline pytest suite under `tests/`; a fixture refuses real Google Cloud clients; artifact tests parse dbt in a temporary directory with dummy settings |
| `make lint` / `make format` | Ruff and Black check / mutate formatting |
| `make api-dev` / `make frontend-dev` | Local API on 8000 / Next.js on 3000 |
| `make frontend-build` | Compile and type-check frontend |
| `make api-test` | Currently targets absent `api/tests/`; do not report API test coverage from it |
| `make frontend-test` | Playwright unit-style specs in `frontend/tests/` (pure functions; no browser or server) |
| `make ingest-all` | The eleven batch ingestors, writing locally by default; still calls external source APIs. The stream poller, backfill, alerts, Veo and job access run separately |
| `make bq-load` | GCS raw loading via realtime date window; not restricted to realtime table types |
| `make dbt-run-staging`, `make dbt-run-core`, `make dbt-run-marts` | Cloud transformations; `dbt-marts` has no recipe |
| `make dbt-artifacts`, `make dbt-docs`, `make pages-build` | Can connect to BigQuery; separate from offline `make test` |

Set `LLM_PROVIDER=stub` for local work; queries still run on BigQuery and need credentials that can read `mart_denver`. `.env.example` selects Gemini; Gemini without a key errors. Set server-side `API_BASE_URL=http://localhost:8000` in `frontend/.env.local`.

## Code map and invariants

- `src/whyline/ingest/`, `load/`: one CLI per source plus the loader, shared I/O, explicit `JobSpec` registry, MD5 load deduplication, and a Cloud Storage lock so only one loader runs at a time.
- `dbt/models/`: medallion layers: 25 silver staging models (`stg_denver`), 33 gold-core Kimball models (`core_denver`: 8 dims, 21 facts, 4 bridges), 35 serving marts (`mart_denver`). Three are legacy and disabled since the stop-visit cutover: `stg_rt_events`, `fct_trip_observation`, `fct_stop_arrival`. Marts read only gold core. Definitions and schemas are the source of truth; see [model reference](dbt/models/README.md).
- `src/whyline/sync/constants.py`: 20 `ALLOWLISTED_MARTS` and 2 `LIVE_MARTS` (live views). API exposure additionally requires manifest `config.meta.allow_in_app`; CSV downloads have a separate 18-mart list.
- `api/models.py`: request/response contract; `frontend/src/types/api.ts` mirrors it. Five routers under `/api`. Query execution always re-sanitizes SQL server-side.
- `src/whyline/sql_guardrails.py`: text checks for early errors (read-only SQL, allowlisted namespaces/tables, default `LIMIT 5000` if absent). Not the security boundary: pass `allowed_tables` and `max_rows` to `bigquery_engine.execute` for any visitor SQL, so BigQuery's dry run re-checks statement type and tables and the fetch is capped.
- `src/whyline/llm.py`: Gemini or stub generation, and `qualify_tables` (bare mart names to `project.mart_denver.table`). Other named providers are not implemented.
- `src/whyline/prebuilt.py`: the 9 ready-made questions as SQL templates (the ninth reads live data), `is_live`, and `clean_filters`, which validates filter-rail values before any SQL uses them. Keep labels in sync with `frontend/src/types/api.ts`.
- `src/whyline/engines/`: BigQuery only (DuckDB was removed November 19, 2026). Route and stop lookups are cached for the life of the process, so verify served results after a rebuild. DuckDB remains a test dependency: `tests/sql/` runs dbt models on small inputs in it.
- `frontend/`: Next.js 15 (React 19), Zustand persistence, TanStack Query, Recharts, Deck.gl. Dynamically import `StopMap` with `ssr: false`.
- `infra/cloud-run/`: one image dispatches `JOB_TYPE=load|stream` (`stream` runs on the poller VM; the old `ingest` mode was removed). Update the job and the VM's `image-uri` to the tested immutable image digest when shared source changes; `:latest` is not automatically refreshed in existing jobs.

Use focused checks appropriate to the change. Do not treat API health, a timestamp, enabled scheduling, completed jobs, actual data coverage, and correct query results as interchangeable evidence. Do not promise complete arrival coverage or describe missing weather as dry. See [metrics](docs/public/METRICS_GLOSSARY.md) for current limitations.
