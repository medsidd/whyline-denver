# Testing and verification

## Existing offline tests

Activate `.venv`, install `requirements.txt`, and run from the repository root:

```bash
make test
make test-ingest
.venv/bin/python -m pytest tests/ingest/test_noaa_daily.py -q
make lint
```

`pyproject.toml` selects `tests/`. Current areas include ingestion contracts/manifests and NOAA behavior, SQL guardrails and route/weather regression tests, LLM handling, dbt artifact parsing, export/refresh logic, a package smoke test, and documentation exporter success/failure checks. Read the actual test files before claiming coverage of an entire subsystem.

Artifact tests parse the current dbt project into temporary output using explicit dummy project/dataset settings and a small catalog fixture. They do not query BigQuery or depend on the checked-in manifest. `make test` is simply `pytest`; it no longer runs `dbt-artifacts`. Credentials are unnecessary for this suite.

The suite must never reach Google Cloud, even when `.env` and application-default credentials are present. An autouse fixture in `tests/conftest.py` makes the Cloud Storage and BigQuery client constructors raise and clears the sync-state bucket variables; `tests/test_offline_guard.py` checks it. Before October 29, 2026 the DuckDB refresh tests overwrote the production warehouse and sync state on every credentialed local run (see [operations](OPERATIONS.md)). A new test that needs a client passes a fake.

`bq_load.py` creates cloud clients in `main()`. Importing it does not itself authenticate clients, but importing configuration loads `.env` and may materialize inline credentials. Prefer reading source for configuration audits.

## Coverage gaps and frontend checks

There is no `api/tests/` or `tests/api/` suite in this checkout. `make api-test` currently points at the absent former directory. Do not describe it as a passing API test suite.

The frontend declares Playwright and maps `npm test` / `make frontend-test` to it, but no specs or Playwright configuration are checked in. Jest/React Testing Library are not configured. Available frontend checks include:

```bash
make frontend-build
cd frontend
npm run lint
```

A build type-checks and compiles; it does not prove the full browser workflow. For manual verification, exercise generation/prebuilt SQL, editing/validation, engine switching, results, map rendering, and both export controls. Use a local DuckDB warehouse and stub LLM to avoid cloud query/provider charges when appropriate.

## BigQuery data quality checks

These commands access BigQuery and may incur charges:

```bash
make dbt-test-staging
make dbt-test-marts
make dbt-source-freshness
```

Model tests live in schema YAML and `dbt/tests/`; inspect the selected models and compiled tests. Do not assume a source-freshness command establishes freshness for every source if no applicable freshness thresholds are declared.

The nightly BigQuery recipe runs transformations, then mart tests, then exports. A failed test prevents that recipe from reaching export. It does not automatically cancel independently scheduled DuckDB or realtime jobs.

## CI and hooks

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`: install, Ruff/Black lint, `make test`, then `make test-ingest`. On successful pushes to `main`, subsequent jobs generate dbt docs using cloud credentials and deploy GitHub Pages. The build/test job is offline; the entire workflow is not.

Passing CI does not prove branch protection is configured or prevent merges by itself. Confirm repository settings separately if that guarantee is needed.

`.pre-commit-config.yaml` runs Ruff, Ruff formatting, and Black, with an explicit exclusion for `src/whyline/ingest/io.py`. `make lint` has its own scope and does not inherit that hook exclusion.

## Add meaningful tests

Mock HTTP/GCS/cloud clients for offline tests. For a data bug, include source missingness and the actual SQL selection/aggregation behavior, not just string comparisons that reproduce the implementation. Test incremental and full-refresh behavior when selection windows change. Test artifact fixtures in a clean environment rather than relying on a developer's `.env`.

For operational changes, verify configuration, completed executions, data content, exports, and served results separately using [QA validation](../QA_Validation_Guide.md). Record exactly which checks ran and which required production access.
