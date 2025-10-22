# WhyLine Denver

![CI Passing](https://img.shields.io/badge/CI-passing-brightgreen.svg)

WhyLine Denver turns raw public transit feeds into a governed, dual-engine analytics experience where anyone can ask questions in natural language and receive cost-capped SQL answers, visualizations, and downloadable datasets—powered by a dbt semantic layer with switchable DuckDB and BigQuery backends.

## Quickstart (Local · DuckDB)

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and populate credentials/secrets
4. `make run`

## Credentials & Secrets

- **NEVER** commit `.env` or any tokens to git. `.env.example` lists the variables the app expects; copy it locally and keep credentials in your environment.
- `NOAA_CDO_TOKEN` (optional) unlocks the live NOAA daily summaries endpoint. If it is unset the ingestor falls back to reading a local CSV (`data/external/noaa_raw.csv`).
- `CENSUS_API_KEY` (optional) raises Census API rate limits. Without it the ACS ingestor still works against the public throttle.
- For GCS writes, ingestion modules rely on Google Application Default Credentials. Locally run `gcloud auth application-default login`, or point `GOOGLE_APPLICATION_CREDENTIALS` at a service-account JSON. In CI we inject the key through GitHub secrets—no keys ever live in the repo.
- Set `WLD_LOG_LEVEL` (default `INFO`) to `DEBUG` when diagnosing ingestion runs; logging remains structured across all scripts.

## Architecture Diagrams

- [Pipeline Architecture](docs/pipeline_architecture.drawio) (coming soon)
- [App Semantic Layer](docs/app_semantic_layer.drawio) (coming soon)

## Team Conventions

- Imports follow `stdlib` → blank line → `third-party` → blank line → `local` groupings; ruff isort enforces this order.
- All new functions must include complete type hints to keep the codebase self-documenting.
- Prefer structured logging (JSON lines) and plan to centralize helpers in `src/whylinedenver/logs.py`.
- Commits use Conventional Commits prefixes (`feat:`, `fix:`, `chore:`, `docs:`, etc.).
- Pull requests include a checklist covering tests run, lint clean, no secrets committed, and screenshots for app UI changes.

## Production Path (BigQuery)

- `gcloud auth application-default login`
- Set `GCP_PROJECT_ID`, dataset names, and bucket values in your `.env`
- Point `ENGINE=bigquery` once the environment is configured

## dbt Usage

- Install dependencies in the repo virtualenv (`pip install -r requirements.txt`) so the bundled `dbt-core`, `dbt-bigquery`, and `dbt-duckdb` adapters are on the Python path.
- `.env.example` now includes `DBT_PROFILES_DIR=dbt/profiles`; the helper resolves it to an absolute path so both dbt CLI and IDE tooling can locate the profile.
- Export (or add to `.env`) `GOOGLE_APPLICATION_CREDENTIALS=/path/to/whyline-dbt-*.json`, `GCP_PROJECT_ID`, and `BQ_DATASET_MART` before running dbt commands.
- Invoke dbt through the helper script: `python -m scripts.dbt_with_env <command> --project-dir dbt ...`. Example: `make dbt-source-freshness` or `python -m scripts.dbt_with_env source freshness --project-dir dbt --target prod`.
- Remove any legacy `dbt`/`dbt-fusion` binaries from your shell (`brew uninstall dbt` or `pipx uninstall dbt-fusion`) so the Homebrew CLI cannot shadow the project-managed dbt core.
- In editors (VS Code/Pylance), be sure to select the repo’s `.venv` interpreter so Python import resolution picks up `python-dotenv`, `dbt-core`, and friends.

### dbt Run Order (BigQuery)

The Makefile bundles the recommended sequence for refreshing staging → intermediate → marts, plus validation and docs. From the repo root:

```bash
export DBT_PROFILES_DIR=$PWD/dbt/profiles   # if not already exported
make dbt-run-staging        # builds stg_denver views
make dbt-run-intermediate   # materialises dependency views in stg_denver
make dbt-run-marts          # builds mart_denver tables (pulls deps automatically)
make dbt-test-staging       # optional: run staging tests
make dbt-test-marts         # validates mart layer
make dbt-docs               # regenerates catalog/manifest for docs site
```

`make dbt-marts` (and the tests) automatically include upstream models, but the explicit intermediate target is useful during local development to spot issues early.

## Freshness Badges

- Planned: surface dbt source and model freshness badges alongside the Streamlit experience

## Data Attributions

- Links to public transit data providers will be added here in a later revision
