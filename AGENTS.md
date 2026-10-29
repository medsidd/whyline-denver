# Repository guidance

## Session startup

1. Invoke `task-observer` before task-oriented work that uses tools and produces deliverables.
2. When loading a skill, read OPEN observations tagged to it in this stable repository's `skill-observations/log.md` and apply active `cross-cutting-principles.md` guidance. Preserve concurrent entries.
3. Read [documentation index](docs/README.md), [operations](docs/technical/OPERATIONS.md), and relevant technical references before editing.
4. Inspect `git status` and preserve unrelated changes. Source code, Makefile recipes, and workflow definitions take precedence over older narrative descriptions.

## Scope and cloud actions

The August pause was superseded by an approved October 2026 restart. Both realtime schedulers and nightly workflows were verified enabled on October 26, 2026; this is dated evidence, not a guarantee of present health. Do not reapply the obsolete freeze or infer permission to change schedules from setup examples.

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
| `make frontend-test` | Invokes Playwright; no checked-in specs/configuration currently exist |
| `make ingest-all` | Seven ingestors writing locally by default; still calls external source APIs |
| `make bq-load` | GCS raw loading via realtime date window; not restricted to realtime table types |
| `make dbt-run-staging`, `make dbt-run-core`, `make dbt-run-marts` | Cloud transformations; `dbt-marts` has no recipe |
| `make sync-duckdb` | BigQuery export then DuckDB refresh, including configured remote uploads; not a warehouse download |
| `make dbt-artifacts`, `make dbt-docs`, `make pages-build` | Can connect to BigQuery; separate from offline `make test` |

Set `ENGINE=duckdb` and `LLM_PROVIDER=stub` explicitly for local work. `.env.example` selects Gemini; Gemini without a key errors. Set server-side `API_BASE_URL=http://localhost:8000` in `frontend/.env.local`.

## Code map and invariants

- `src/whyline/ingest/`, `load/`: seven CLIs, shared I/O, explicit `JobSpec` registry, MD5 load deduplication.
- `dbt/models/`: medallion layers: 17 silver staging models (`stg_denver`), 15 gold-core Kimball models (`core_denver`: 6 dims, 8 facts, 1 bridge), nine serving marts (`mart_denver`). Marts read only gold core. Definitions and schemas are the source of truth; see [model reference](dbt/models/README.md).
- `src/whyline/sync/constants.py`: nine `ALLOWLISTED_MARTS`. API exposure additionally requires manifest `config.meta.allow_in_app`; CSV downloads have a separate seven-mart list.
- `api/models.py`: request/response contract; `frontend/src/types/api.ts` mirrors it. Five routers under `/api`. Query execution always re-sanitizes SQL server-side.
- `src/whyline/sql_guardrails.py`: read-only SQL, allowlisted namespaces/tables, default `LIMIT 5000` if absent. Existing limits are preserved, not capped.
- `src/whyline/llm.py`: Gemini or stub generation and SQL dialect adaptation. Other named providers are not implemented.
- `src/whyline/engines/`: BigQuery and DuckDB. Use `DUCKDB_COPY_LOCAL=1` on Cloud Run; connections and lookups are cached, so verify served results after warehouse replacement.
- `frontend/`: Next.js 14, Zustand persistence, TanStack Query, Recharts, Deck.gl. Dynamically import `StopMap` with `ssr: false`.
- `infra/cloud-run/`: one image dispatches `JOB_TYPE=ingest|load`. Update both jobs to the tested immutable image digest when shared source changes; `:latest` is not automatically refreshed in existing jobs.

Use focused checks appropriate to the change. Do not treat API health, a timestamp, enabled scheduling, completed jobs, actual data coverage, and correct query results as interchangeable evidence. Do not promise complete arrival coverage or describe missing weather as dry. See [metrics](docs/public/METRICS_GLOSSARY.md) for current limitations.
