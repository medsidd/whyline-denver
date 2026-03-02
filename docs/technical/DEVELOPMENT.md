# Development Setup

This document covers how to set up a local development environment, what environment variables are needed, and the make targets you'll use day-to-day.

---

## Prerequisites

- **Python 3.11** — other versions are untested
- **Node.js 18+** and npm — for the frontend
- **GCP project** — required for BigQuery engine; optional for DuckDB-only development
- **Gemini API key** — required for LLM SQL generation; the stub provider works offline without it

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/medsidd/whyline-denver.git
cd whyline-denver

# 2. Set up Python environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install                # pip install + pre-commit hooks

# 3. Configure environment
cp .env.example .env
# Edit .env — minimum required for local DuckDB use:
#   GEMINI_API_KEY=<your key>  (or leave LLM_PROVIDER=stub to skip LLM)

# 4. Download data and start servers
make sync-duckdb            # Download pre-built warehouse from GCS (~several MB)
make api-dev                # FastAPI at http://localhost:8000
make frontend-dev           # Next.js at http://localhost:3000 (separate terminal)
```

For the frontend to reach the API, create `frontend/.env.local`:

```bash
echo "API_BASE_URL=http://localhost:8000" > frontend/.env.local
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values you need. The `.env` file is loaded automatically by the Python package at import time (via python-dotenv).

### GCP and BigQuery

| Variable | Default | Required for |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | `whyline-denver` | BigQuery engine, Cloud Run deployment |
| `GCP_REGION` | `us-central1` | Cloud Run deployment |
| `GCS_BUCKET` | `whylinedenver-raw` | Ingest to GCS, sync operations |
| `BQ_DATASET_RAW` | `raw_denver` | BigQuery loader |
| `BQ_DATASET_STG` | `stg_denver` | dbt staging + intermediate |
| `BQ_DATASET_MART` | `mart_denver` | dbt marts, API queries |
| `GOOGLE_APPLICATION_CREDENTIALS` | _(none)_ | GCP authentication (path to JSON key, or inline JSON) |
| `DBT_PROFILES_DIR` | `dbt/profiles` | dbt project configuration |
| `DBT_TARGET` | `prod` | dbt target profile |
| `MAX_BYTES_BILLED` | `2000000000` | BigQuery query cost cap (2 GB) |

### DuckDB

| Variable | Default | Notes |
|----------|---------|-------|
| `ENGINE` | `bigquery` | Default query engine. Set to `duckdb` for local dev |
| `DUCKDB_GCS_BLOB` | `marts/duckdb/warehouse.duckdb` | GCS path to warehouse within bucket |
| `DUCKDB_PARQUET_ROOT` | `data/marts` | Local Parquet cache directory |
| `DUCKDB_PATH` | _(computed)_ | Resolved to `data/warehouse.duckdb` locally, `/mnt/gcs/marts/duckdb/warehouse.duckdb` on Cloud Run |

### Sync state

| Variable | Default | Notes |
|----------|---------|-------|
| `SYNC_STATE_GCS_BUCKET` | `whylinedenver-raw` | Bucket for sync_state.json |
| `SYNC_STATE_GCS_BLOB` | `state/sync_state.json` | Path within bucket |

### LLM

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | `stub` | `gemini` for production, `stub` for testing without API calls |
| `GEMINI_API_KEY` | _(none)_ | Required when `LLM_PROVIDER=gemini` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model version |

### Data ingestion

| Variable | Default | Notes |
|----------|---------|-------|
| `NOAA_CDO_TOKEN` | _(none)_ | Free token from [NOAA CDO](https://www.ncdc.noaa.gov/cdo-web/token). Falls back to local CSV if unset. |
| `CENSUS_API_KEY` | _(none)_ | Optional. Requests without a key are rate-limited but work. |

### Frontend (frontend/.env.local)

| Variable | Notes |
|----------|-------|
| `API_BASE_URL` | Required. Set to `http://localhost:8000` for local dev, Cloud Run URL for production |

---

## Make Targets Reference

### Development servers

```bash
make api-dev          # FastAPI at http://localhost:8000 with hot reload
make frontend-dev     # Next.js at http://localhost:3000 with hot reload
make app              # Streamlit legacy dashboard at http://localhost:8501
```

### Testing and quality

```bash
make test             # Full pytest suite (requires dbt artifacts in dbt/target/)
make test-ingest      # Ingestor smoke tests (no network required)
make lint             # ruff check + black --check
make format           # ruff fix + black format (auto-fixes in place)
make api-test         # API endpoint tests
make dbt-test-staging # dbt data quality tests on staging layer
make dbt-test-marts   # dbt data quality tests on marts
```

### Ingestion

```bash
make ingest-all           # All 7 ingestors, local output
make ingest-all-gcs       # All 7 ingestors, write to GCS
make ingest-gtfs-static   # RTD GTFS schedules
make ingest-gtfs-rt       # RTD realtime snapshot (1 snapshot)
make ingest-crashes       # Denver crashes (5-year rolling)
make ingest-sidewalks     # Denver sidewalk segments
make ingest-noaa          # NOAA weather (requires --start and --end in underlying call)
make ingest-acs           # Census ACS demographics
make ingest-tracts        # Census TIGER tract boundaries
```

### BigQuery loading

```bash
make bq-load              # Load today's data to BigQuery
make bq-load-local        # Load from data/raw/ to BigQuery
make bq-load-realtime     # Load only today's GTFS-RT snapshots
make bq-load-historical FROM=2025-01-01 UNTIL=2025-01-31  # Backfill range
```

### dbt transformation

```bash
make dbt-run-staging      # Run stg_* models
make dbt-run-intermediate # Run int_* models
make dbt-run-marts        # Run mart_* models
make dbt-run-realtime     # Optimized realtime subset (every-5-min use)
make dbt-compile          # Compile without executing
make dbt-parse            # Parse and validate models
make dbt-docs             # Generate and serve dbt docs at localhost:8080
make dbt-source-freshness # Check raw source table freshness
```

### Sync and warehouse

```bash
make sync-export          # Export BigQuery marts to GCS Parquet
make sync-refresh         # Refresh DuckDB from GCS Parquet
make sync-duckdb          # Both: sync-export then sync-refresh
make update-bq-timestamp  # Update sync_state.json BigQuery freshness timestamp
```

### Nightly orchestration targets

```bash
make nightly-ingest-bq    # Ingest all + bq-load (run by nightly-ingest workflow)
make nightly-bq           # dbt-run-marts + sync-export (run by nightly-bq workflow)
make nightly-duckdb       # sync-refresh (run by nightly-duckdb workflow)
```

### Full local dev loop

```bash
make dev-loop-local       # ingest-all + bq-load-local + dbt-run-marts + sync-duckdb
make dev-loop-gcs         # ingest-all-gcs + bq-load + dbt-run-marts + sync-duckdb
```

### Frontend

```bash
make frontend-dev         # Start dev server
make frontend-build       # Type-check + production build
make frontend-test        # Jest tests
```

---

## Running Tests

Tests require dbt artifacts to exist:

```bash
make dbt-artifacts        # Generates dbt/target/manifest.json (needed for tests)
make test                 # Run all 28 pytest tests
```

To run a single test:

```bash
.venv/bin/python -m pytest tests/path/to/test_file.py::test_function_name -q
```

**Note**: `bq_load` tests import the module at test time, which triggers GCP authentication. This will hang if GCP credentials are not configured. Use `PYTHONPATH=src .venv/bin/python -c "import whyline"` to check basic imports quickly.

---

## dbt Setup

dbt profiles are in `dbt/profiles/profiles.yml`. The profile `whyline_denver` has two targets:

- `prod`: uses `GCP_PROJECT_ID`, `BQ_DATASET_*` env vars — for production BigQuery
- `demo`: uses the same env vars but with `DBT_TARGET=demo` — for a separate isolated environment

Local dbt commands run against whichever target `DBT_TARGET` is set to (default `prod` in config.py, `demo` in `.env.example`).

```bash
# Check that dbt can connect
dbt debug --profiles-dir dbt/profiles

# Compile to check SQL syntax without executing
make dbt-compile
```

---

## Pre-commit Hooks

`make install` sets up pre-commit hooks that run ruff and black on every `git commit`:

```bash
make install     # First-time setup
pre-commit run --all-files   # Run manually against all files
```

To bypass in an emergency (not recommended):

```bash
git commit --no-verify -m "message"
```

---

## Common Issues

**Import check hangs**: `import whyline.load.bq_load` triggers GCP authentication at import time. This is expected behavior — use `PYTHONPATH=src .venv/bin/python -c "import whyline"` for basic import testing.

**DuckDB file not found**: Run `make sync-duckdb` to download the warehouse from GCS. If you don't have GCS access, set `ENGINE=bigquery` in `.env`.

**dbt tests fail**: dbt artifacts (`dbt/target/manifest.json`, `catalog.json`) must exist. Run `make dbt-artifacts` to generate them.

**Frontend can't reach API**: Ensure `frontend/.env.local` contains `API_BASE_URL=http://localhost:8000` and the API dev server is running.

**LLM returns no SQL**: If `GEMINI_API_KEY` is not set, the API falls back to `LLM_PROVIDER=stub` which returns mock SQL. Set `LLM_PROVIDER=gemini` and add your key for real generation.
