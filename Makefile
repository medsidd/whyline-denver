.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
.PHONY: install lint format test test-ingest run app demo ingest-all ingest-all-local ingest-all-gcs ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts bq-load bq-load-local dbt-source-freshness dbt-parse dbt-test-staging dbt-run-staging dbt-marts dbt-marts-test dbt-docs dbt-run-preflight dev-loop ci-help sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb
.PHONY: sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb

# Shared command helpers ------------------------------------------------------
PYTHON        := python
PIP           := pip
PY_ENV        := PYTHONPATH=$$PWD/src
PY            := $(PY_ENV) $(PYTHON)

INGEST_DEST   ?= local
INGEST_MODE_ARGS := $(if $(filter $(INGEST_DEST),gcs),--gcs --bucket $(GCS_BUCKET),--local)

DBT_PROFILES  := DBT_PROFILES_DIR=$$PWD/dbt/profiles
DBT_CMD       := $(DBT_PROFILES) $(PY) -m scripts.dbt_with_env
DBT_TARGET    ?= prod

GCS_BUCKET    ?= whylinedenver-raw

# Tooling ---------------------------------------------------------------------
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	pre-commit install

lint:
	ruff check . && black --check .

format:
	ruff check . --fix && black .

test: dbt-artifacts
	pytest

dbt-artifacts:
	@if [ ! -f dbt/target/manifest.json ] || [ ! -f dbt/target/catalog.json ]; then \
		DBT_TARGET=demo $(DBT_CMD) parse --project-dir dbt --target demo; \
		DBT_TARGET=demo $(DBT_CMD) docs generate --project-dir dbt --target demo; \
	fi


test-ingest:
	pytest -k ingest

run: app

app:
	$(PY) -m streamlit run app/streamlit_app.py

DEMO_ENV := GCP_PROJECT_ID=demo-project BQ_DATASET_RAW=raw_local BQ_DATASET_STG=stg_local BQ_DATASET_MART=mart_local DUCKDB_PATH=data/warehouse.duckdb

demo:
	mkdir -p data
	$(DBT_CMD) deps --project-dir dbt --no-use-colors || true
	$(DEMO_ENV) $(DBT_CMD) parse --project-dir dbt --no-use-colors --target demo
	$(DEMO_ENV) $(DBT_CMD) run --project-dir dbt --no-use-colors --target demo --select 'staging marts'
	$(DEMO_ENV) $(DBT_CMD) docs generate --project-dir dbt --no-use-colors --target demo

# Ingest ----------------------------------------------------------------------
ingest-all: ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts

ingest-gtfs-static:
	$(PY) -m whylinedenver.ingest.gtfs_static $(INGEST_MODE_ARGS)

ingest-gtfs-rt:
	$(PY) -m whylinedenver.ingest.gtfs_realtime $(INGEST_MODE_ARGS) --snapshots 2 --interval-sec 90

ingest-crashes:
	$(PY) -m whylinedenver.ingest.denver_crashes $(INGEST_MODE_ARGS)

ingest-sidewalks:
	$(PY) -m whylinedenver.ingest.denver_sidewalks $(INGEST_MODE_ARGS)

ingest-noaa:
	$(PY) -m whylinedenver.ingest.noaa_daily $(INGEST_MODE_ARGS) --start 2025-10-10 --end 2025-10-30

ingest-acs:
	$(PY) -m whylinedenver.ingest.acs $(INGEST_MODE_ARGS) --year 2023 --geo tract

ingest-tracts:
	$(PY) -m whylinedenver.ingest.denver_tracts $(INGEST_MODE_ARGS)

ingest-all-local:
	@$(MAKE) INGEST_DEST=local ingest-all

ingest-all-gcs:
	@$(MAKE) INGEST_DEST=gcs ingest-all

bq-load:
	$(PY) -m load.bq_load --src gcs --bucket $(GCS_BUCKET) --since 2025-01-01

bq-load-local:
	$(PY) -m load.bq_load --src local --bucket $(GCS_BUCKET) --since 2025-01-01

sync-export:
	@set -euo pipefail; \
	ARGS=""; \
	if [ -n "$${SINCE:-}" ]; then \
		ARGS="$$ARGS --since $${SINCE}"; \
	fi; \
	if [ -n "$${MARTS:-}" ]; then \
		for MART in $$MARTS; do \
			ARGS="$$ARGS --mart $$MART"; \
		done; \
	fi; \
	$(PY) -m whylinedenver.sync.export_bq_marts $$ARGS

sync-refresh:
	@set -euo pipefail; \
	ARGS=""; \
	if [ -n "$${LOCAL_PARQUET_ROOT:-}" ]; then \
		ARGS="$$ARGS --local-parquet-root $${LOCAL_PARQUET_ROOT}"; \
	fi; \
	if [ -n "$${DUCKDB_PATH:-}" ]; then \
		ARGS="$$ARGS --duckdb-path $${DUCKDB_PATH}"; \
	fi; \
	if [ -n "$${LOG_LEVEL:-}" ]; then \
		ARGS="$$ARGS --log-level $${LOG_LEVEL}"; \
	fi; \
	if [ -n "$${DRY_RUN:-}" ]; then \
		ARGS="$$ARGS --dry-run"; \
	fi; \
	$(PY) -m whylinedenver.sync.refresh_duckdb $$ARGS

sync-duckdb: sync-export sync-refresh

nightly-ingest-bq:
	@$(MAKE) INGEST_DEST=gcs ingest-all
	$(MAKE) bq-load

nightly-bq:
	@set -euo pipefail; \
	DBT_TARGET=prod $(DBT_CMD) run --project-dir dbt --target prod --select 'staging marts'; \
	DBT_TARGET=prod $(DBT_CMD) test --project-dir dbt --target prod --select 'marts'; \
	$(MAKE) sync-export

nightly-duckdb:
	$(MAKE) sync-refresh

# dbt -------------------------------------------------------------------------
dbt-source-freshness:
	$(DBT_CMD) source freshness --project-dir dbt --target $(DBT_TARGET) --select source:raw

dbt-parse:
	$(DBT_CMD) parse --project-dir dbt --target $(DBT_TARGET)

dbt-run-staging:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'staging.*'

dbt-run-intermediate:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'intermediate.*'

dbt-run-marts:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select 'marts.*'

dbt-test-staging:
	$(DBT_CMD) test --project-dir dbt --target $(DBT_TARGET) --select 'staging.*'

dbt-test-marts:
	$(DBT_CMD) test --project-dir dbt --target $(DBT_TARGET) --select marts

dbt-docs:
	$(DBT_CMD) docs generate --project-dir dbt --target $(DBT_TARGET)

# Workflows -------------------------------------------------------------------
dev-loop:
	$(MAKE) ingest-all-local
	$(MAKE) bq-load-local
	DBT_TARGET=prod $(MAKE) dbt-parse
	DBT_TARGET=prod $(MAKE) dbt-run-staging
	DBT_TARGET=prod $(MAKE) dbt-run-intermediate
	DBT_TARGET=prod $(MAKE) dbt-run-marts
	DBT_TARGET=prod $(MAKE) dbt-test-staging
	DBT_TARGET=prod $(MAKE) dbt-test-marts
	DBT_TARGET=prod $(MAKE) dbt-source-freshness
	DBT_TARGET=prod $(MAKE) dbt-docs
	$(MAKE) sync-duckdb

ci-help:
	@echo "Targets: install | lint | format | test | run | demo | ingest-* | bq-load(-local) | dbt-* | dev-loop"
.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
