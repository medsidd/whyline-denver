# Development setup

Run commands from the repository root. Use Python 3.11 and a Node.js version compatible with the locked Next.js 14.2.5 (at least 18.17). The frontend is `frontend/`; the old Streamlit application is absent even though some legacy dependencies remain installed.

## Install and configure

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make install
pip install -r api/requirements.txt
cp .env.example .env
```

Do not overwrite an existing `.env`. Edit the copy to select local behavior:

```dotenv
ENGINE=duckdb
LLM_PROVIDER=stub
DUCKDB_PATH=data/warehouse.duckdb
DUCKDB_COPY_LOCAL=0
SYNC_STATE_GCS_BUCKET=
```

The last setting makes freshness read local `data/sync_state.json`. `.env.example` otherwise points to the project bucket and selects Gemini. Environment values already exported in the shell take precedence because `load_dotenv(override=False)` is used. Do not import `config.py` merely to inspect values: inline credential handling can write a credential file.

### Warehouse and artifacts

An existing DuckDB file is required for data queries. With authorized read access to the project bucket:

```bash
mkdir -p data
gcloud storage cp gs://whylinedenver-raw/marts/duckdb/warehouse.duckdb data/warehouse.duckdb
gcloud storage cp gs://whylinedenver-raw/state/sync_state.json data/sync_state.json
```

Alternatively use a trusted supplied warehouse; there is no bundled full offline data bootstrap. Avoid `make sync-duckdb` for downloading: it exports BigQuery marts, refreshes a local warehouse, and attempts configured remote uploads.

API model/schema operations also need `dbt/target/manifest.json` and `catalog.json`. Obtain matching artifacts from the successful CI/nightly artifact outputs or generate them against BigQuery when cloud access is intended. A checked-in/generated local snapshot may be stale; compare `/api/models` with the [model inventory](../../dbt/models/README.md). `make dbt-artifacts` can run compile/parse/docs generation if artifacts are missing and credentials are present. It is not offline setup.

### Start the application

```bash
make api-dev
```

In another terminal:

```bash
cd frontend
npm ci
# Create .env.local with API_BASE_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000/app`; FastAPI OpenAPI is at `http://localhost:8000/docs`. If Next.js reports `EMFILE` watcher errors on this Mac, use `WATCHPACK_POLLING=1000 npm run dev`. If dependencies are incomplete, restore them with `npm ci` before changing application code.

## Settings and their actual defaults

Defaults below come from code; `.env.example`, Makefile variables, and deployment settings can override them.

| Setting | Code behavior / purpose |
|---|---|
| `ENGINE` | `bigquery` in `Settings`; API generation request and browser default to `duckdb` |
| `GCP_PROJECT_ID`, `GCS_BUCKET` | `whyline-denver`, `whylinedenver-raw` |
| `BQ_DATASET_RAW`, `BQ_DATASET_STG`, `BQ_DATASET_MART` | `raw_denver`, `stg_denver`, `mart_denver` |
| `MAX_BYTES_BILLED` | 2,000,000,000 bytes for the API BigQuery query engine |
| `GOOGLE_APPLICATION_CREDENTIALS` | Credential file path; code also accepts inline JSON. Prefer managed credentials/ADC; never commit values. |
| `DBT_PROFILES_DIR`, `DBT_TARGET` | Wrapper/Makefile use `dbt/profiles`, `prod`; example env selects `demo`. Inspect `dbt/profiles/profiles.yml`. |
| `DUCKDB_PATH` | Query engine defaults to `data/warehouse.duckdb`; set explicitly for other locations |
| `DUCKDB_COPY_LOCAL`, `DUCKDB_LOCAL_PATH` | Copy enabled unless `0`; temporary `warehouse.duckdb` by default. Use `1` with Cloud Run's GCS mount. |
| `DUCKDB_GCS_BLOB`, `DUCKDB_PARQUET_ROOT` | `marts/duckdb/warehouse.duckdb`, `data/marts` for synchronization |
| `DUCKDB_MAX_AGE_DAYS` | 90 for partitioned history during refresh |
| `SYNC_STATE_GCS_BUCKET`, `SYNC_STATE_GCS_BLOB` | Remote state enabled only when bucket is set; blob defaults to `state/sync_state.json` |
| `LLM_PROVIDER` | `stub` when unset in provider dispatch; `.env.example` and deployment Makefile select `gemini` |
| `GEMINI_API_KEY` / `LLM_API_KEY` | Gemini key / fallback key; Gemini selection without either errors |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `NOAA_CDO_TOKEN` | NOAA API access; without it weather uses `data/external/noaa_raw.csv`, which must exist and use metric units |
| `CENSUS_API_KEY` | Code allows omission, but production workflow maps the configured secret; inspect response errors rather than assuming keyless access succeeds |
| `WLD_LOG_LEVEL` | `INFO` for shared ingestion logging |
| `API_BASE_URL` | Next.js server-side proxy target in `frontend/.env.local`; no `NEXT_PUBLIC_` prefix |

`ENABLE_BIGQUERY` and `APP_*` values left in `.env.example` are not a supported frontend feature switch or branding mechanism. Verify consumers before relying on a template entry. The deployment Makefile uses `CLOUD_RUN_REGION`, not `GCP_REGION`, for region selection.

## Commands by side effect

| Command | Effect |
|---|---|
| `make test`, `make test-ingest` | Offline Python suite / ingestion-selected subset |
| `make lint`, `make format` | Check / change Python formatting |
| `make frontend-build` | Compile/type-check; may fetch configured web fonts |
| `make ingest-all`, `make ingest-all-local` | Calls source APIs, writes local raw data; not offline |
| `make ingest-all-gcs` | Calls source APIs and uploads raw data |
| `make bq-load-local` | Loads local files into BigQuery, starting from 2025-01-01 |
| `make bq-load`, `make bq-load-realtime` | Same date-window GCS loader; scans all registered source types |
| `make dbt-parse` | Parses models; no warehouse query, but requires profile environment values |
| `make dbt-compile`, `make dbt-docs`, `make dbt-artifacts` | Can contact BigQuery; docs target generates files rather than serving them |
| `make dbt-run-staging`, `make dbt-run-core`, `make dbt-run-marts` | Run cloud transformations |
| `make sync-export`, `make sync-refresh`, `make sync-duckdb` | Export, refresh, or both; can write GCS/state/warehouse |
| `make api-deploy` | Builds and deploys Cloud Run |

`make app` and `make run` have no recipes. The broad `dev-loop-*` recipes are cloud operations; `dev-loop-local` also uploads to GCS and ends in a nonexistent `run` target. Use explicit stages instead. See [testing](TESTING.md) for unavailable API/Playwright targets.

After a package rename, inspect `src/*.egg-info`; remove only confirmed obsolete generated metadata and reinstall with `.venv/bin/pip install -e .`.
