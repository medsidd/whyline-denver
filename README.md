# WhyLine Denver

[Dashboard](https://www.whylinedenver.com/app) · [Documentation](docs/README.md) · [Operating status and costs](docs/technical/OPERATIONS.md)

WhyLine Denver combines RTD transit feeds, Denver crash and sidewalk records, NOAA weather, and Census demographics into a transit analytics dashboard. It helps investigate reliability, safety, equity, and access. Ask a question, review the generated SQL, then run it to see tables, charts, maps, and downloadable results.

Since October 29, 2026 every stop visit is timed from RTD's vehicle reports (about every 30 seconds); earlier dates come from 15-minute samples. Questions about right now read live data that trails real time by 15–30 minutes. It does not provide trip planning, arrival predictions or passenger counts, and some trips go unseen.

## How it works

```text
RTD / Denver Open Data / NOAA / Census / others
  → Python ingestion (incl. a continuous GTFS-RT poller) → GCS raw files → BigQuery raw_denver
  → dbt stg_denver → core_denver → mart_denver
  → FastAPI → Next.js dashboard (every query runs on BigQuery)
```

BigQuery builds the warehouse and answers every query. The project has 16 ingestion CLIs, 93 dbt models in medallion layers (25 silver staging, 33 gold-core Kimball dimensions/facts/bridges, 35 serving marts, two of them live views), and a Next.js 15 / React 19 frontend. Python dependencies are in `requirements.txt` and `api/requirements.txt`; frontend versions are locked in `frontend/package-lock.json`.

Realtime data comes from a continuous poller on a VM, loaded every 15 minutes by the `realtime-load` job. Nightly Ingest requests 08:17 UTC; Nightly BigQuery starts when it finishes. See [operations](docs/technical/OPERATIONS.md) for dated evidence, billing, and verification commands.

## Run locally

Use Python 3.11, Node.js 18.17 or later compatible with the locked Next.js version, and npm. Run from the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make install
pip install -r api/requirements.txt
cp .env.example .env
```

Edit `.env`: set `LLM_PROVIDER=stub`. The example file selects Gemini; a missing Gemini key does not automatically select the stub. Stub mode supports canned SQL without a paid LLM call.

Queries run on BigQuery, so the API needs Google credentials that can read `mart_denver` and run query jobs (`gcloud auth application-default login`). See [development setup](docs/technical/DEVELOPMENT.md) for artifacts and configuration.

In separate terminals with the environment activated:

```bash
make api-dev
```

```bash
cd frontend
npm ci
# Create .env.local containing: API_BASE_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000/app`. API docs are at `http://localhost:8000/docs`. API schema endpoints also need usable `dbt/target/manifest.json` and `catalog.json`; a successful health response alone does not establish that those artifacts or BigQuery access are available.

## Where to work

| Path | Responsibility |
|---|---|
| `src/whyline/ingest/`, `load/` | Public-source extraction, manifests, explicit BigQuery schemas, MD5 deduplication |
| `dbt/models/` | SQL transformations and data quality assertions |
| `src/whyline/sync/` | The app's mart list and the BigQuery freshness record |
| `src/whyline/engines/`, `semantics/` | BigQuery query engine and dbt schema/allowlist loading |
| `api/` | SQL generation, validation, execution, filters, and downloads |
| `frontend/` | Dashboard, visualizations, browser state |
| `infra/`, `.github/workflows/` | Cloud images, scheduled processing, CI |

## Contributing and checks

GitHub's default branch is `main` (verified October 26, 2026). Create a branch from the intended current base and inspect the PR target; the old instruction requiring all PRs to target `dev` is no longer supported by current CI/default-branch configuration.

```bash
make test              # offline Python suite under tests/
make lint              # Ruff and Black checks
make frontend-build    # Next.js type check and production compilation
```

`make api-test` points to an absent `api/tests/` directory. Playwright is declared but there are no checked-in frontend specs/configuration. See [testing](docs/technical/TESTING.md) for the actual coverage and gaps.

## Reading next

- [Public overview](docs/public/OVERVIEW.md), [data coverage](docs/public/DATA_SOURCES.md), and [metrics](docs/public/METRICS_GLOSSARY.md).
- [Architecture](docs/technical/ARCHITECTURE.md), [pipeline](docs/technical/DATA_PIPELINE.md), and [model reference](dbt/models/README.md).
- [Deployment](docs/technical/DEPLOYMENT.md) and [operations](docs/technical/OPERATIONS.md).
- [Cost optimization lessons](docs/case-studies/bigquery-cost-optimization-2025.md) and [pipeline recovery lessons](docs/case-studies/pipeline-recovery-2026.md).

Source-specific terms apply: [RTD](https://www.rtd-denver.com/open-records/open-spatial-information/gtfs-realtime-license-agreement), [Denver Open Data](https://opendata-geospatialdenver.hub.arcgis.com/), and the source agencies' terms for NOAA and Census data. Do not infer a blanket license from public availability.
