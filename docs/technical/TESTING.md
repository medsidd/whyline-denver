# Testing

WhyLine Denver has three testing layers: a Python pytest suite, dbt data quality tests, and TypeScript frontend tests.

---

## Python Tests (pytest)

**Location**: `tests/`
**Count**: 28 tests
**Command**: `make test`

### Prerequisites

dbt artifacts must exist before running tests:

```bash
make dbt-artifacts   # Generates dbt/target/manifest.json and catalog.json
make test
```

Or run a single test without make:

```bash
.venv/bin/python -m pytest tests/path/to/test_file.py::test_function_name -q
```

### Test categories

**Ingestor tests** (`tests/ingest/`): Unit tests for each of the 7 ingestors. These test parsing logic, normalization, geometry calculations, and manifest generation without making network calls. Designed to run offline using sample data fixtures.

**API tests** (`tests/api/`): Tests for API endpoint behavior, SQL guardrail rules, LLM prompt building, and result enrichment. Uses FastAPI's test client.

**Engine tests**: Tests for BigQuery and DuckDB engine adapters — SQL adaptation, dialect translation, caching behavior.

**Sync tests**: Tests for the mart export and DuckDB refresh logic.

### Known behaviors

**`bq_load` import hang**: Importing `whyline.load.bq_load` triggers GCP authentication at module load time. This is expected — the test suite skips or mocks this import where needed. A bare `python -c "import whyline"` check will succeed because the top-level package `__init__.py` does not import `bq_load`.

To check basic imports quickly:

```bash
PYTHONPATH=src .venv/bin/python -c "import whyline; print('ok')"
```

---

## dbt Data Quality Tests

dbt tests run SQL assertions against the actual data in BigQuery. They check for nulls, duplicates, referential integrity, and value ranges.

**Commands**:

```bash
make dbt-test-staging   # Tests on staging layer (nulls, uniqueness, accepted values)
make dbt-test-marts     # Tests on mart layer (range checks, referential integrity)
make dbt-source-freshness  # Checks that raw source tables are not stale
```

Tests are defined in `dbt/models/staging/schema.yml` and `dbt/models/marts/schema.yml`. The nightly BigQuery workflow fails and alerts if any test fails before the mart export step.

### Test coverage (partial list)

- `stg_gtfs_stops`: stop_id is not null, stop_id is unique, lat/lon are in valid ranges
- `stg_rt_events`: feed_ts_utc is not null, arrival_delay_sec is within [-3600, 7200]
- `mart_reliability_by_route_day`: route_id is not null, pct_on_time is between 0 and 1
- `mart_priority_hotspots`: stop_id is not null, priority_score is not negative
- `mart_vulnerability_by_stop`: vuln_score_0_100 is between 0 and 100

---

## Frontend Tests

**Command**: `make frontend-test` or `cd frontend && npm test`

TypeScript/JavaScript tests use Jest and React Testing Library. Coverage is focused on utility functions and component rendering.

---

## CI Pipeline

The CI workflow (`ci.yml`) runs on every pull request and push to `main`:

```
Lint (ruff + black)
    ↓
pytest (28 tests)
    ↓
Ingest smoke tests
    ↓ (only on push to main)
dbt docs build → GitHub Pages deploy
```

If any step fails, the workflow stops and the PR is blocked from merging.

### Ingest smoke tests

```bash
make test-ingest
```

These tests verify that each ingestor CLI parses arguments correctly and handles edge cases (empty inputs, missing fields, out-of-range coordinates) without making real network calls.

---

## Pre-commit Hooks

`make install` installs pre-commit hooks that run automatically on `git commit`:

```
ruff check --fix   (linting + auto-fix)
black --check      (formatting check)
```

To run all hooks manually:

```bash
pre-commit run --all-files
```

---

## Writing New Tests

### For a new ingestor

1. Add a test file in `tests/ingest/test_<module_name>.py`
2. Use the pattern from existing ingestor tests: create sample raw data, call `normalize_records()` directly, assert on the output DataFrame
3. Do not make real network calls — use `monkeypatch` or `unittest.mock` to intercept HTTP requests

### For a new API endpoint

1. Add tests in `tests/api/`
2. Use `from fastapi.testclient import TestClient` with the app from `api.main`
3. Mock engine calls if needed — the test client runs in-process

### For a new dbt model

Add tests to the appropriate schema.yml file:

```yaml
models:
  - name: mart_new_metric
    columns:
      - name: stop_id
        tests:
          - not_null
          - relationships:
              to: ref('mart_gtfs_stops')
              field: stop_id
      - name: score
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100
```
