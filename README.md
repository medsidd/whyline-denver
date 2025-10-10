# WhyLine Denver

![CI Passing](https://img.shields.io/badge/CI-passing-brightgreen.svg)

WhyLine Denver turns raw public transit feeds into a governed, dual-engine analytics experience where anyone can ask questions in natural language and receive cost-capped SQL answers, visualizations, and downloadable datasets—powered by a dbt semantic layer with switchable DuckDB and BigQuery backends.

## Quickstart (Local · DuckDB)

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and populate credentials/secrets
4. `make run`

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

## Freshness Badges

- Planned: surface dbt source and model freshness badges alongside the Streamlit experience

## Data Attributions

- Links to public transit data providers will be added here in a later revision
