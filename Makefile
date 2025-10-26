.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
.PHONY: install lint format test test-ingest run app ingest-all ingest-all-local ingest-all-gcs ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts bq-load bq-load-local dbt-source-freshness dbt-parse dbt-test-staging dbt-run-staging dbt-marts dbt-marts-test dbt-docs dbt-run-preflight dev-loop ci-help sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb pages-build deploy-hf
.PHONY: sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb pages-build deploy-hf

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
		$(DBT_CMD) parse --project-dir dbt --target $(DBT_TARGET); \
		$(DBT_CMD) docs generate --project-dir dbt --target $(DBT_TARGET); \
	fi


test-ingest:
	pytest -k ingest

run: app

app:
	$(PY) -m streamlit run app/streamlit_app.py

# Ingest ----------------------------------------------------------------------
ingest-all: ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts

# Ingest without realtime (realtime handled by hourly workflow)
ingest-static: ingest-gtfs-static ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts

ingest-gtfs-static:
	$(PY) -m whylinedenver.ingest.gtfs_static $(INGEST_MODE_ARGS)

ingest-gtfs-rt:
	$(PY) -m whylinedenver.ingest.gtfs_realtime $(INGEST_MODE_ARGS) --snapshots 2 --interval-sec 90

ingest-crashes:
	$(PY) -m whylinedenver.ingest.denver_crashes $(INGEST_MODE_ARGS)

ingest-sidewalks:
	$(PY) -m whylinedenver.ingest.denver_sidewalks $(INGEST_MODE_ARGS)

ingest-noaa:
	@set -euo pipefail; \
	START_DATE=$$(date -u -v-30d +%Y-%m-%d 2>/dev/null || date -u -d '30 days ago' +%Y-%m-%d); \
	END_DATE=$$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d); \
	$(PY) -m whylinedenver.ingest.noaa_daily $(INGEST_MODE_ARGS) --start $$START_DATE --end $$END_DATE

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
	@$(MAKE) INGEST_DEST=gcs ingest-static
	$(MAKE) bq-load

nightly-ingest-bq-full:
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
dev-loop-local:
	$(MAKE) ingest-all-local
	$(MAKE) ingest-all-gcs
	$(MAKE) bq-load-local
	$(MAKE) bq-load
	DBT_TARGET=prod $(MAKE) dbt-parse
	DBT_TARGET=prod $(MAKE) dbt-run-staging
	DBT_TARGET=prod $(MAKE) dbt-run-intermediate
	DBT_TARGET=prod $(MAKE) dbt-run-marts
	DBT_TARGET=prod $(MAKE) dbt-test-staging
	DBT_TARGET=prod $(MAKE) dbt-test-marts
	DBT_TARGET=prod $(MAKE) dbt-source-freshness
	DBT_TARGET=prod $(MAKE) dbt-docs
	$(MAKE) sync-duckdb
	$(MAKE) run

dev-loop-gcs:
	$(MAKE) ingest-all-gcs
	$(MAKE) bq-load
	DBT_TARGET=prod $(MAKE) dbt-parse
	DBT_TARGET=prod $(MAKE) dbt-run-staging
	DBT_TARGET=prod $(MAKE) dbt-run-intermediate
	DBT_TARGET=prod $(MAKE) dbt-run-marts
	DBT_TARGET=prod $(MAKE) dbt-test-staging
	DBT_TARGET=prod $(MAKE) dbt-test-marts
	DBT_TARGET=prod $(MAKE) dbt-source-freshness
	DBT_TARGET=prod $(MAKE) dbt-docs
	$(MAKE) sync-duckdb

pages-build:
	@echo "Building dbt documentation for GitHub Pages..."
	$(MAKE) dbt-docs
	@echo "Preparing site directory..."
	@mkdir -p site
	@echo "Copying documentation artifacts..."
	@cp -r dbt/target/* site/
	@echo "✓ Documentation build complete!"

deploy-hf:
	python scripts/deploy_hf.py

ci-help:
	@echo "Targets: install | lint | format | test | run | ingest-* | bq-load(-local) | dbt-* | dev-loop"

.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
