# WhyLine Denver

![CI](https://github.com/medsidd/whyline-denver/actions/workflows/ci.yml/badge.svg)
![Nightly Ingest](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-ingest.yml/badge.svg)
![Nightly BQ](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-bq.yml/badge.svg)
![Nightly DuckDB](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-duckdb.yml/badge.svg)

**A transit data platform that makes Denver's bus and train data accessible, queryable, and equity-focused.**

WhyLine Denver ingests six public data sources — RTD schedules and realtime positions, traffic crashes, sidewalk infrastructure, weather, and census demographics — into a unified analytics warehouse. Ask questions in plain English and get back SQL, charts, and CSVs. No GTFS expertise required.

The project has a specific focus on equity: transit-dependent populations often experience worse service. WhyLine Denver makes those patterns visible by combining reliability data with demographics, designed to help planners, advocates, and policymakers see where improvements would matter most.

---

## How It Works

```
RTD / NOAA / Census / Denver Open Data
             │
             ▼
    GCS (raw, partitioned)
             │
             ▼
   BigQuery (raw_denver)
             │
             ▼
   dbt: stg_denver → mart_denver      ← 25 SQL models, 40+ quality tests
             │
      ┌──────┴──────┐
      ▼             ▼
  BigQuery       GCS Parquet → DuckDB (local, free)
      └──────┬──────┘
             ▼
          FastAPI
             │
             ▼
       Next.js dashboard
    (natural language → SQL → results)
```

**Realtime**: Cloud Run Jobs capture RTD vehicle positions every 5 minutes, 24 hours a day.

**Nightly**: GitHub Actions workflows (8–9:30 AM UTC) refresh schedules, crashes, weather, sidewalks, and demographics; run dbt transformations; and sync the DuckDB warehouse.

---

## What's Inside

```
src/whyline/ingest/   — 7 ingestors (GTFS static, GTFS-RT, crashes, sidewalks, weather, ACS, tracts)
src/whyline/load/     — BigQuery parametric loader with MD5-based deduplication
src/whyline/engines/  — BigQuery + DuckDB query engines (dual-engine pattern)
src/whyline/sync/     — Mart export to Parquet + DuckDB warehouse refresh
dbt/models/           — 25 SQL models: 10 staging → 6 intermediate → 9 marts
api/                  — FastAPI: 5 routers, 12 endpoints
frontend/             — Next.js 14 dashboard (Zustand, Recharts, Deck.gl)
infra/cloud-run/      — Cloud Run job image for realtime ingest (JOB_TYPE dispatch)
.github/workflows/    — CI + 3 nightly workflows
tests/                — 28 pytest tests
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Languages | Python 3.11, TypeScript, SQL |
| Data warehouse | BigQuery (cloud), DuckDB (local embedded) |
| Transformation | dbt 1.8 |
| Orchestration | Cloud Run Jobs + Cloud Scheduler (realtime), GitHub Actions (nightly) |
| Storage | Google Cloud Storage |
| API | FastAPI (uvicorn) |
| Frontend | Next.js 14, React 18, Zustand, Recharts, Deck.gl |
| LLM | Google Gemini (gemini-2.5-flash) for SQL generation |
| Testing | pytest, dbt tests, pre-commit (ruff + black) |

---

## Quickstart — Local (DuckDB, no GCP required)

```bash
# 1. Clone and create a Python virtual environment
git clone https://github.com/medsidd/whyline-denver.git
cd whyline-denver
python -m venv .venv && source .venv/bin/activate
make install          # installs dependencies + pre-commit hooks

# 2. Configure environment
cp .env.example .env
# ENGINE=duckdb is already set in .env.example
# Optionally set GEMINI_API_KEY for LLM SQL generation (falls back to stub mode without it)

# 3. Download the pre-built data warehouse
make sync-duckdb      # requires read access to the GCS bucket (see note below)

# 4. Start the servers
make api-dev          # FastAPI → http://localhost:8000
make frontend-dev     # Next.js → http://localhost:3000
```

> **Note on `make sync-duckdb`**: This downloads the warehouse file from Google Cloud Storage. It requires GCP credentials (`gcloud auth application-default login`) or a `GOOGLE_APPLICATION_CREDENTIALS` env var pointing to a service account key. For a fully offline setup without GCP access, see [docs/technical/DEVELOPMENT.md](docs/technical/DEVELOPMENT.md).

### Full production setup (BigQuery + Cloud Run)

See [docs/technical/DEVELOPMENT.md](docs/technical/DEVELOPMENT.md) for the complete environment setup and [docs/technical/DEPLOYMENT.md](docs/technical/DEPLOYMENT.md) for Cloud Run and Vercel deployment.

---

## Data Sources

| Source | Data | Frequency |
|--------|------|-----------|
| RTD | Bus/train schedules (GTFS static) | Nightly |
| RTD | Realtime vehicle positions (GTFS-RT) | Every 5 min |
| Denver Open Data | Traffic crashes, sidewalk segments | Nightly |
| NOAA | Daily weather (station USW00023062) | Nightly (3–7 day lag) |
| U.S. Census ACS | Tract-level demographics (2023 5-year) | Annual |
| U.S. Census TIGER | Tract boundaries (2020) | Decennial |

All data is public and non-PII. See [docs/public/DATA_SOURCES.md](docs/public/DATA_SOURCES.md) for full coverage details, known limitations, and licenses.

---

## Documentation

### For developers

| Document | Description |
|----------|-------------|
| [docs/technical/ARCHITECTURE.md](docs/technical/ARCHITECTURE.md) | System design, dual-engine pattern, infrastructure, cost model |
| [docs/technical/DATA_PIPELINE.md](docs/technical/DATA_PIPELINE.md) | All 7 ingestors, BigQuery loading, 25 dbt models, DuckDB sync |
| [docs/technical/API_REFERENCE.md](docs/technical/API_REFERENCE.md) | All 12 endpoints with request/response examples |
| [docs/technical/FRONTEND.md](docs/technical/FRONTEND.md) | Component tree, Zustand state, chart auto-detection |
| [docs/technical/DEVELOPMENT.md](docs/technical/DEVELOPMENT.md) | Local setup, env vars, all make targets, common errors |
| [docs/technical/DEPLOYMENT.md](docs/technical/DEPLOYMENT.md) | Cloud Run, Vercel, GitHub Actions secrets, Cloud Scheduler |
| [docs/technical/TESTING.md](docs/technical/TESTING.md) | pytest suite, dbt tests, CI pipeline |
| [dbt/models/README.md](dbt/models/README.md) | All 25 dbt models with schemas, materializations, and tests |
| [docs/README.md](docs/README.md) | Full documentation index |

### Guides

| Document | Description |
|----------|-------------|
| [ADDING_A_DATA_SOURCE.md](docs/technical/guides/ADDING_A_DATA_SOURCE.md) | How to add an 8th ingestor |
| [ADDING_A_MART.md](docs/technical/guides/ADDING_A_MART.md) | How to add a new dbt mart |
| [ADAPTING_TO_OTHER_CITIES.md](docs/technical/guides/ADAPTING_TO_OTHER_CITIES.md) | How to adapt this for a different city |

### For transit planners and the public

| Document | Description |
|----------|-------------|
| [docs/public/OVERVIEW.md](docs/public/OVERVIEW.md) | What WhyLine Denver is, in plain English |
| [docs/public/HOW_IT_WORKS.md](docs/public/HOW_IT_WORKS.md) | From bus stop to dashboard answer — no jargon |
| [docs/public/METRICS_GLOSSARY.md](docs/public/METRICS_GLOSSARY.md) | Plain-English definitions of every metric |
| [docs/public/USE_CASES.md](docs/public/USE_CASES.md) | Example workflows for planners, council members, and riders |
| [docs/public/DATA_SOURCES.md](docs/public/DATA_SOURCES.md) | Data coverage, freshness, and limitations |
| [docs/public/FAQ.md](docs/public/FAQ.md) | Common questions answered without technical jargon |

---

## Contributing

Contributions are welcome. The active development branch is `dev` — open all PRs there, not `main`.

### Setup

```bash
git clone https://github.com/medsidd/whyline-denver.git
cd whyline-denver
git checkout dev

python -m venv .venv && source .venv/bin/activate
make install          # installs dependencies + pre-commit hooks (ruff + black)
cp .env.example .env
```

### Development workflow

1. Create a branch off `dev`:
   ```bash
   git checkout -b feat/your-feature
   ```

2. Make changes. Then before committing:
   ```bash
   make format   # auto-fix formatting with ruff + black
   make lint     # verify no remaining lint errors
   make test     # all 28 pytest tests must pass
   ```

3. Pre-commit hooks run `ruff` and `black` automatically on each commit (installed by `make install`). If a hook fails, fix the issue and recommit — do not use `--no-verify`.

4. Commit using [Conventional Commits](https://www.conventionalcommits.org/) format:

   | Prefix | Use for |
   |--------|---------|
   | `feat:` | New feature |
   | `fix:` | Bug fix |
   | `docs:` | Documentation only |
   | `refactor:` | Code restructure without behavior change |
   | `test:` | Adding or updating tests |
   | `chore:` | Tooling, dependencies, CI configuration |

5. Open a PR against `dev`. CI runs automatically: lint, tests, and (on merge to `main`) dbt docs build.

### Code standards

- All new Python functions must have complete type annotations
- New ingestors and engines must include unit tests in `tests/`
- SQL models must include a corresponding schema YAML with dbt tests
- See [ADDING_A_DATA_SOURCE.md](docs/technical/guides/ADDING_A_DATA_SOURCE.md) and [ADDING_A_MART.md](docs/technical/guides/ADDING_A_MART.md) for step-by-step guides

### Running a subset of tests

```bash
# Single test file
.venv/bin/python -m pytest tests/test_gtfs_static.py -q

# Single test
.venv/bin/python -m pytest tests/test_gtfs_static.py::test_parse_routes -q

# All tests with output
make test
```

See [docs/technical/TESTING.md](docs/technical/TESTING.md) for the full test guide.

---

## Data Licenses

| Source | License |
|--------|---------|
| RTD (schedules + positions) | [RTD Open Data License](https://www.rtd-denver.com/open-data-license) |
| Denver Open Data Portal (crashes, sidewalks) | [Open Database License](https://www.denvergov.org/opendata/terms) |
| NOAA/NCEI (weather) | Public domain |
| U.S. Census Bureau (ACS, TIGER) | Public domain |

---

**Questions?** Open an [issue](https://github.com/medsidd/whyline-denver/issues) or check the [GitHub Actions logs](https://github.com/medsidd/whyline-denver/actions).
