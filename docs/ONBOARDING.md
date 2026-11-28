# Onboarding: learn WhyLine Denver end to end

This is a path through the project for a developer who has never seen it. Work through it in order. Each stage says what to read, what to run, and how to check you understood it before moving on. Plan on about a week at a relaxed pace; stages 1–4 fit in two days.

The other docs are the reference; this one is the route through them. When this guide and the code disagree, the code wins. Tell the maintainer, and fix whichever is wrong.

## What the project is, in one paragraph

WhyLine Denver (whylinedenver.com) lets anyone ask a plain-English question about Denver's buses and trains. A Python pipeline collects public data (RTD schedules and live vehicle feeds, crashes, weather, census, sidewalks and more) into Google Cloud. dbt turns it into tidy tables in BigQuery. A FastAPI service asks Gemini to write SQL for the question. It shows the SQL first, checks that it only reads approved tables, runs it on BigQuery, and returns rows. A Next.js dashboard on Vercel shows the result as a table, chart or map.

```text
Public sources ──► Python ingestion ──► GCS raw files ──► BigQuery raw_denver
   (RTD, Denver,       (src/whyline/ingest)     (gs://whylinedenver-raw/raw/)
    NOAA, Census…)
                                                     │  dbt (dbt/models)
                                                     ▼
                     stg_denver (staging) ──► core_denver (dims, facts) ──► mart_denver (35 marts)
                                                                                 │
     Browser ──► Next.js on Vercel ──/api/*──► FastAPI on Cloud Run ──► BigQuery mart_denver
     (frontend/)      (rewrites)              (api/, src/whyline)       (20 app marts + 2 live views)

Live data: a poller VM reads RTD's feeds every 15 s ──► 15-minute batches ──► realtime-load job
(Cloud Run) loads them and rebuilds the stop-visit tables, so "right now" questions trail by 15–30 min.
Nightly: GitHub Actions run Nightly Ingest (static sources) and then Nightly BigQuery (dbt build + tests).
```

## Stage 0: get access

Ask the maintainer for:

| What | Why | Without it |
|---|---|---|
| Read access to the GitHub repo (it is public) and write access if you'll open PRs | Code, Actions history | Read-only work only |
| A Google account with `roles/bigquery.jobUser` on project `whyline-denver` and reader on `mart_denver` | The local API runs every query on BigQuery | You can read code and run the offline tests, but the app shows no data |
| Optional: reader on `raw_denver`, `stg_denver`, `core_denver` and the bucket `whylinedenver-raw` | Tracing data back through the pipeline (stage 5) | Stage 5 becomes reading-only |
| Optional: a Gemini API key | Real question-to-SQL locally | Use `LLM_PROVIDER=stub`, which returns canned SQL |

Never commit or paste credentials, `.env`, service-account JSON or keys. Production changes go through the maintainer: deploys, IAM, scheduler and workflow changes, `dbt run` against prod, and bucket deletes ([AGENTS.md](../AGENTS.md) has the rules).

## Stage 1: use the product (1 hour)

1. Open https://www.whylinedenver.com and read the landing page top to bottom.
2. Open the dashboard (`/app`). Try three of the "ready-made questions": "Worst 10 routes by on-time share", "Stops with highest crash exposure", "Which routes are running right now?". For each one, read the SQL in step 2 before running it, then switch between Chart, Map and Table.
3. Type your own question, for example "Which routes had the most delay yesterday?", and press Write SQL. Edit the SQL by hand: add a `LIMIT 3`, then try `DELETE FROM mart_gtfs_routes` and watch it get refused.
4. Set a route in the Filters rail and reload a ready-made question; see where the filter lands in the SQL.
5. Read the public docs in this order: [overview](public/OVERVIEW.md), [how it works](public/HOW_IT_WORKS.md), [FAQ](public/FAQ.md), then skim [metrics glossary](public/METRICS_GLOSSARY.md) (what "on time" means, why figures change on October 29, 2026).

**Check yourself:** Why does "running right now" lag by 15–30 minutes? What does the app do with SQL that names a table outside the app's list?

## Stage 2: read the map of the code (2 hours)

Read these in order. Don't read every file yet; learn where things live.

1. [README.md](../README.md): the short tour.
2. [AGENTS.md](../AGENTS.md): commands, code map, invariants and the rules for cloud changes. Read this one carefully; it applies to you too.
3. [docs/README.md](README.md): the index of every doc.
4. [Architecture](technical/ARCHITECTURE.md): the layers, the query boundary (why the SQL check is in three layers), caching and hosting.

Then open the folders and match them to the architecture:

| Folder | What lives there | Start with |
|---|---|---|
| `src/whyline/ingest/` | One CLI per data source (16), plus the realtime stream poller | `gtfs_static.py`, then `gtfs_rt_stream.py` (long; skim its top docstring) |
| `src/whyline/load/` | The GCS → BigQuery loader: explicit schemas, MD5 de-duplication, a lock | `registry.py` (every raw table), `bq_load.py` |
| `dbt/models/` | SQL transformations: `staging/`, `core/`, `marts/` | [dbt/models/README.md](../dbt/models/README.md) |
| `src/whyline/` (top level) | `sql_guardrails.py` (text checks), `llm.py` (prompt, Gemini, table qualification), `prebuilt.py` (the 9 ready-made questions), `logs.py` (query log and caches) | `prebuilt.py` |
| `src/whyline/engines/bigquery_engine.py` | Dry run, the allowed-table check, execution with a byte cap | the whole file (short) |
| `src/whyline/semantics/` | Reads dbt's manifest/catalog to know which marts and columns the app may use | `dbt_artifacts.py` |
| `src/whyline/sync/` | The app's mart list and the "Data updated" freshness record | `constants.py` |
| `api/` | FastAPI app: `main.py`, `models.py` (request/response contract), `routers/` | `routers/sql.py`, `routers/query.py` |
| `frontend/` | Next.js 15 / React 19 dashboard | `src/app/app/page.tsx`, `src/lib/api.ts`, `src/store/dashboardStore.ts` |
| `infra/` | Cloud Run job image (`cloud-run/`), the poller VM (`stream-vm/`), API build (`api-service/`) | `infra/cloud-run/README.md` |
| `.github/workflows/` | CI, Nightly Ingest, Nightly BigQuery, Weekly Job Access, a manual realtime load | [workflows README](../.github/workflows/README.md) |
| `tests/` | Offline Python tests; many run dbt models on small inputs in DuckDB | [testing](technical/TESTING.md) |

**Check yourself:** Name the three BigQuery datasets the dbt layers write to, and the one the app reads. Where is the list of marts the app is allowed to query?

## Stage 3: run it locally (half a day)

Follow [development](technical/DEVELOPMENT.md); the short version:

```bash
git clone https://github.com/medsidd/whyline-denver.git && cd whyline-denver
python3.11 -m venv .venv && source .venv/bin/activate
make install                       # requirements.txt + pre-commit hooks
pip install -r api/requirements.txt
cp .env.example .env               # then edit it, see below
make test                          # offline: never touches Google Cloud
make lint
```

Edit `.env`:

- `LLM_PROVIDER=stub` unless you have a Gemini key.
- `SYNC_STATE_GCS_BUCKET=` (empty) to read freshness from the local `data/sync_state.json`.
- `DBT_TARGET=prod`. The example file says `demo`, but the dbt profile only defines `prod`, so dbt commands fail with `demo`.

Then sign in for BigQuery and start both halves, in two terminals:

```bash
gcloud auth application-default login     # an account from stage 0
make api-dev                              # http://localhost:8000/docs
```

```bash
cd frontend
npm ci
echo "API_BASE_URL=http://localhost:8000" > .env.local
npm run dev                               # http://localhost:3000/app
```

The API needs `dbt/target/manifest.json` and `catalog.json` to know the marts. They are in the repo; if `/api/models` comes back empty, see "Data access and artifacts" in the development doc.

Every query you run locally is a real BigQuery query and is billed (each is capped at 2 GB by `MAX_BYTES_BILLED`). Prefer the ready-made questions and small `LIMIT`s while learning.

**Check yourself:**

- `curl -s localhost:8000/api/health` returns `{"status":"ok"}`.
- `curl -s localhost:8000/api/filters` lists routes.
- The dashboard runs "Worst 10 routes by on-time share" and shows a chart.
- `make test` passes (about 215 tests).

## Stage 4: follow one question through the code (half a day)

This is the most useful exercise in the guide. Pick "Which routes had the most delay yesterday?" and trace it, opening each file as you go.

1. **Browser.** `frontend/src/components/steps/Step1QuestionInput.tsx` calls `generateSql` in `frontend/src/lib/api.ts`, which POSTs `/api/sql/generate`. `frontend/next.config.mjs` rewrites `/api/*` to the API (`API_BASE_URL`), so the browser never talks to Cloud Run directly.
2. **Generate.** `api/routers/sql.py::generate_sql`:
   - builds a prompt (`src/whyline/llm.py::build_prompt`) from the question, the filters, today's Denver date and a schema brief made from dbt's catalog;
   - calls Gemini (`call_provider`);
   - injects the filter-rail predicates (`_add_filter_clauses`);
   - runs the text checks (`src/whyline/sql_guardrails.py::sanitize_sql`);
   - qualifies table names (`qualify_tables`).
3. **Validate.** The dashboard shows the SQL and calls `/api/sql/validate`. `bigquery_engine.estimate` does a **dry run**: BigQuery parses the SQL and reports the statement type, the tables it would read and the bytes. `_check_reads` refuses anything but one SELECT over the app's marts. This, not the regex text check, is the real gate.
4. **Run.** `/api/query/run` (`api/routers/query.py`) repeats the checks and runs the query with `bigquery_engine.execute`: the dry run again, then the job with `maximum_bytes_billed`, a 120 s timeout and at most 10,000 rows fetched. It adds stop and route names from `mart_gtfs_stops`/`mart_gtfs_routes`, logs the query (hashes only, `src/whyline/logs.py`) and returns rows.
5. **Display.** `frontend/src/components/steps/Step3Results.tsx` picks a chart or map from the columns (`frontend/src/lib/chartLogic.ts`). Maps are Deck.gl over MapLibre (`components/viz/StopMap.tsx`), with route lines from `/api/routes/shapes`.

Then do the same for a ready-made question: `src/whyline/prebuilt.py` holds the 9 SQL templates, and `POST /api/sql/prebuilt/{index}` fills in the filters and a default date window in Denver days.

**Check yourself:**

- Why is `sanitize_sql` "not the security boundary"? Find a query that passes it but fails the dry-run check. `tests/sql/test_engine_guards.py` has examples.
- Where would you change how many rows the dashboard displays?

## Stage 5: follow the data from source to mart (1 day)

Read [data pipeline](technical/DATA_PIPELINE.md), then trace one fact: "the on-time share of route 15 yesterday".

1. **Schedule.** `src/whyline/ingest/gtfs_static.py` downloads RTD's GTFS zip nightly to `gs://whylinedenver-raw/raw/rtd_gtfs/extract_date=…/`. `load/registry.py` maps each file to a raw table (`raw_gtfs_stop_times` …). `bq_load.py` loads only files whose MD5 it hasn't seen (`raw_denver.__ingestion_log`).
2. **Live positions.** The poller (`gtfs_rt_stream.py`, on the VM `rt-stream-poller`) reads RTD's vehicle-position and trip-update feeds every 15 seconds. It works out when each bus reached each stop, and writes a batch every 15 minutes to `raw/rtd_gtfsrt_stream/`. Every 15 minutes the `realtime-load` Cloud Run job loads the batches into `raw_gtfsrt_stop_visits` and friends, then runs a small dbt selection (`make dbt-run-realtime`).
3. **dbt.**
   - `stg_rt_stop_visits` (a view) becomes `fct_stop_visit` (one row per trip × stop × day, with `delay_sec`).
   - That feeds `mart_reliability_by_route_day` (`pct_on_time` per route and day).
   - Read those three SQL files and their entries in the `schema.yml` files.
   - Read the macro `dbt/macros/extracts.sql`: it picks the newest extract partitions.
4. **Query it yourself** (BigQuery console or `bq`, with a date filter so it stays cheap):

   ```sql
   SELECT service_date_mst, pct_on_time, n_events, pct_observed
   FROM `whyline-denver.mart_denver.mart_reliability_by_route_day`
   WHERE route_id = '15' AND service_date_mst >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 7 DAY)
   ORDER BY 1;
   ```

5. Read [raw contracts](contracts/CONTRACTS.md) for one source, and [BigQuery naming and time](guides/BQ_Naming_and_Time.md): Denver vs UTC dates trip everyone up.

**Check yourself:**

- Why are on-time figures lower from October 29, 2026? (`data_version`; see the glossary.)
- What happens to a raw file that was already loaded?
- Which dbt models run every 15 minutes, and which only nightly?

## Stage 6: how it runs in production (half a day)

Read [deployment](technical/DEPLOYMENT.md), [operations](technical/OPERATIONS.md) (start with the newest dated sections at the bottom, then "Refresh state read-only") and [infra/cloud-run/README.md](../infra/cloud-run/README.md).

| Piece | Where | How it updates |
|---|---|---|
| Frontend | Vercel project `whyline-denver` | Every merge to `main` deploys automatically |
| API | Cloud Run service `whylinedenver-api` | `make api-deploy` (Cloud Build, then deploy); the maintainer runs it |
| Realtime load | Cloud Run job `realtime-load`, Cloud Scheduler every 15 min | New image digest via `gcloud run jobs update` |
| Stream poller | VM `rt-stream-poller` (container image from its `image-uri` metadata) | New digest in metadata + restart |
| Nightly batch | GitHub Actions: Nightly Ingest (08:17 UTC, often hours late) → Nightly BigQuery | Merges to `main` take effect at the next run |
| Data | BigQuery `raw_denver`, `stg_denver`, `core_denver`, `mart_denver`; bucket `whylinedenver-raw`; archive `whylinedenver-rt-archive` | Pipeline only; never by hand |
| Alerts | Cloud Monitoring: stream batch missing, poller heartbeat missing | Email to the maintainer |

Read-only status checks you can run any time:

```bash
curl -s https://www.whylinedenver.com/api/freshness
gh run list --repo medsidd/whyline-denver --limit 10
gcloud run jobs executions list --job=realtime-load --region=us-central1 --project=whyline-denver --limit=5
```

**Check yourself:**

- A merged dbt fix: when does it reach the nightly tables, and when does it reach the 15-minute job?
- Why does `make api-deploy` matter after a change in `api/` but not after a change in `frontend/`?

## Stage 7: make a first change (1 day)

Pick a small, real task (the maintainer will suggest one), or one of these practice tasks on a branch you don't merge:

- **Add a ready-made question.** Add a template to `src/whyline/prebuilt.py` and a test in `tests/sql/test_prebuilt.py`, then check it in the dashboard.
- **Add a column to a mart.** Follow [adding a mart](technical/guides/ADDING_A_MART.md): SQL, `schema.yml` description and test, then a DuckDB-backed test under `tests/sql/`, as the existing ones do.

The working rules:

- One PR per piece of work. Run `make test`, `make lint` and, for frontend changes, `cd frontend && npm run lint && npm test && npm run build` before pushing. CI runs the same.
- Update the docs in the same PR: the reference doc for what you changed, and a dated note in [operations](technical/OPERATIONS.md) for anything that affects production.
- Check data claims with a real query, not with a successful job.
- Anything that touches production goes through the maintainer: deploys, IAM, scheduler or workflow runs, `dbt run --target prod`, deletes.

## Where to look when something is wrong

| Symptom | First place to look |
|---|---|
| Dashboard shows no data or an error | Browser network tab on `/api/*`, then Cloud Run logs for `whylinedenver-api` |
| "Data updated" time is old | Actions → Nightly Ingest / Nightly BigQuery; `realtime-load` executions |
| Live questions empty | Poller heartbeat in Cloud Logging (`RT_STREAM_HEARTBEAT`), the stream alert emails, `raw_gtfsrt_vp_stream` newest row |
| A number looks wrong | [QA validation](QA_Validation_Guide.md), the model's SQL and `schema.yml`, the glossary's definition |
| A query is refused | The `error` text; `sql_guardrails.py` and `bigquery_engine._check_reads` |

## Glossary of project terms

| Term | Meaning |
|---|---|
| App marts | The 20 tables in `sync/constants.py::ALLOWLISTED_MARTS` that the app may query, plus 2 live views (`LIVE_MARTS`) |
| Live views | `mart_vehicles_now`, `mart_stop_visits_recent`: read the newest 15-minute load directly |
| Stop visit | One bus at one stop on one trip on one service day, timed by the poller (`fct_stop_visit`) |
| `data_version` | How a stop visit was measured: `stream_v1` from October 29, 2026, older days sampled |
| Service date (MST) | RTD's operating day in Denver time; trips after midnight belong to the previous day |
| Dry run | A free BigQuery parse that reports tables and bytes without running; the API's real SQL gate |
| Sync state | `gs://whylinedenver-raw/state/sync_state.json`, holding the "Data updated" time |
