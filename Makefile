.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
.PHONY: install lint format test test-ingest run app ingest-all ingest-all-local ingest-all-gcs ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts bq-load bq-load-local bq-load-realtime bq-load-historical dbt-source-freshness dbt-parse dbt-test-staging dbt-run-staging dbt-marts dbt-marts-test dbt-docs dbt-run-preflight dbt-run-realtime dev-loop ci-help sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb pages-build export-diagrams
.PHONY: sync-export sync-refresh sync-duckdb nightly-ingest-bq nightly-bq nightly-duckdb pages-build export-diagrams dbt-run-realtime streamlit-build streamlit-run

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

# Cloud Run app defaults keep a single instance hot when needed with scale-to-zero otherwise
GCP_PROJECT_ID    ?= whyline-denver
CLOUD_RUN_REGION  ?= us-central1
CLOUD_RUN_DUCKDB_BLOB ?= marts/duckdb/warehouse.duckdb
CLOUD_RUN_MIN_INSTANCES ?= 0  # Allow scale-to-zero for low idle cost
CLOUD_RUN_MAX_INSTANCES ?= 1  # Cap to control spend; adjust if traffic demands
CLOUD_RUN_CONCURRENCY ?= 80   # High per-instance concurrency keeps a single instance busy
CLOUD_RUN_IMAGE  ?= whylinedenver-realtime
CLOUD_RUN_REPO   ?= realtime-jobs
GCS_BUCKET       ?= whylinedenver-raw
STREAMLIT_IMAGE  ?= whylinedenver-app
LLM_PROVIDER     ?= gemini
GEMINI_MODEL     ?= gemini-2.5-flash
GEMINI_API_KEY   ?=
GEMINI_API_KEY_SECRET ?= gemini-api-key:latest

CLOUD_RUN_STREAMLIT_GEMINI_FLAG := $(if $(strip $(GEMINI_API_KEY_SECRET)),--set-secrets GEMINI_API_KEY=$(GEMINI_API_KEY_SECRET),--set-env-vars GEMINI_API_KEY=$(GEMINI_API_KEY))

# Cloud Run Streamlit deployment defaults
CLOUD_RUN_STREAMLIT_REPO      ?= streamlit-app
CLOUD_RUN_STREAMLIT_IMAGE     ?= whylinedenver-app:latest
CLOUD_RUN_STREAMLIT_IMAGE_URI ?= $(CLOUD_RUN_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/$(CLOUD_RUN_STREAMLIT_REPO)/$(CLOUD_RUN_STREAMLIT_IMAGE)
CLOUD_RUN_STREAMLIT_SERVICE   ?= whylinedenver-app
CLOUD_RUN_STREAMLIT_SA        ?= streamlit-app@$(GCP_PROJECT_ID).iam.gserviceaccount.com
CLOUD_RUN_STREAMLIT_MIN_INSTANCES ?= 0
CLOUD_RUN_STREAMLIT_MAX_INSTANCES ?= 3
CLOUD_RUN_STREAMLIT_CONCURRENCY  ?= 10
CLOUD_RUN_STREAMLIT_CPU          ?= 8
CLOUD_RUN_STREAMLIT_MEMORY       ?= 4Gi
MAX_BYTES_BILLED ?= 2000000000  # 2 GB default max bytes billed for queries

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
	STREAMLIT_SERVER_BASEURLPATH="" $(PY) -m streamlit run app/streamlit_app.py

# Ingest ----------------------------------------------------------------------
ingest-all: ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ingest-tracts

# Ingest without realtime (realtime handled by cloud run workflow)
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
	@$(MAKE) bq-load-realtime

bq-load-local:
	$(PY) -m load.bq_load --src local --bucket $(GCS_BUCKET) --from 2025-01-01

bq-load-realtime:
	@set -euo pipefail; \
	NOW_HOUR=$$(date -u +%H); \
	if [ "$$NOW_HOUR" -lt 6 ]; then \
		FROM_DATE=$$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d); \
	else \
		FROM_DATE=$$(date -u +%Y-%m-%d); \
	fi; \
	UNTIL_DATE=$$(date -u +%Y-%m-%d); \
	$(PY) -m load.bq_load --src gcs --bucket $(GCS_BUCKET) --from $$FROM_DATE --until $$UNTIL_DATE

bq-load-historical:
	@set -euo pipefail; \
	FROM_DATE=$${FROM:-2025-01-01}; \
	UNTIL_DATE=$${UNTIL:-$$(date -u +%Y-%m-%d)}; \
	$(PY) -m load.bq_load --src gcs --bucket $(GCS_BUCKET) --from $$FROM_DATE --until $$UNTIL_DATE; \
	DBT_TARGET=prod $(DBT_CMD) run --project-dir dbt --target prod --select 'staging marts'; \
	DBT_TARGET=prod $(DBT_CMD) test --project-dir dbt --target prod --select 'marts'

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
	export DUCKDB_GCS_BLOB="$(CLOUD_RUN_DUCKDB_BLOB)"; \
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

dbt-run-realtime:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select +mart_reliability_by_stop_hour +mart_reliability_by_route_day +mart_weather_impacts --exclude int_scheduled_arrivals

dbt-run-static:
	$(DBT_CMD) run --project-dir dbt --target $(DBT_TARGET) --select int_scheduled_arrivals --full-refresh

# Update BigQuery freshness timestamp in sync_state.json after dbt runs
update-bq-timestamp:
	$(PY) -m whylinedenver.sync.update_bq_timestamp

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

export-diagrams:
	@echo "Exporting draw.io diagrams to SVG/PNG..."
	@bash scripts/export_diagrams.sh

cloud-run-build:
	@docker build -t $(CLOUD_RUN_IMAGE) -f deploy/cloud-run/Dockerfile .

cloud-run-tag:
	@docker tag $(CLOUD_RUN_IMAGE) $(CLOUD_RUN_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/$(CLOUD_RUN_REPO)/$(CLOUD_RUN_IMAGE)

cloud-run-push: cloud-run-tag
	@docker push $(CLOUD_RUN_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/$(CLOUD_RUN_REPO)/$(CLOUD_RUN_IMAGE)

streamlit-build:
	docker build -t $(STREAMLIT_IMAGE) .

streamlit-run: streamlit-build
	@ENV_MOUNT=""; \
	if [ -f .env ]; then \
		ENV_MOUNT="-v $$PWD/.env:/app/.env:ro"; \
	fi; \
	if [ -n "$$GOOGLE_APPLICATION_CREDENTIALS" ]; then \
		echo "→ Mounting GOOGLE_APPLICATION_CREDENTIALS from $$GOOGLE_APPLICATION_CREDENTIALS"; \
			docker run --rm \
			$$ENV_MOUNT \
			-p 8080:8080 \
			-e GCP_PROJECT_ID=$(GCP_PROJECT_ID) \
			-e GCP_REGION=$(CLOUD_RUN_REGION) \
			-e GCS_BUCKET=$(GCS_BUCKET) \
			-e DUCKDB_GCS_BLOB=$(CLOUD_RUN_DUCKDB_BLOB) \
			-e DUCKDB_PARQUET_ROOT=data/marts \
			-e SYNC_STATE_GCS_BUCKET=$(GCS_BUCKET) \
			-e SYNC_STATE_GCS_BLOB=state/sync_state.json \
			-e GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/sa.json \
			-v "$$GOOGLE_APPLICATION_CREDENTIALS":/var/secrets/sa.json:ro \
			$(STREAMLIT_IMAGE); \
	else \
		echo "⚠️  GOOGLE_APPLICATION_CREDENTIALS not set; running without BigQuery access."; \
			docker run --rm \
			$$ENV_MOUNT \
			-p 8080:8080 \
			-e GCP_PROJECT_ID=$(GCP_PROJECT_ID) \
			-e GCP_REGION=$(CLOUD_RUN_REGION) \
			-e GCS_BUCKET=$(GCS_BUCKET) \
			-e DUCKDB_GCS_BLOB=$(CLOUD_RUN_DUCKDB_BLOB) \
			-e DUCKDB_PARQUET_ROOT=data/marts \
			-e SYNC_STATE_GCS_BUCKET=$(GCS_BUCKET) \
			-e SYNC_STATE_GCS_BLOB=state/sync_state.json \
			$(STREAMLIT_IMAGE); \
	fi

artifact-repo-create-streamlit:
	gcloud artifacts repositories create $(CLOUD_RUN_STREAMLIT_REPO) \
	  --project $(GCP_PROJECT_ID) \
	  --repository-format=docker \
	  --location $(CLOUD_RUN_REGION) \
	  --description "WhyLine Streamlit images"

cloud-run-build-streamlit:
	gcloud builds submit \
		--tag $(CLOUD_RUN_STREAMLIT_IMAGE_URI) \
		--project $(GCP_PROJECT_ID) \
		--region $(CLOUD_RUN_REGION) \
		.

cloud-run-deploy-streamlit: cloud-run-build-streamlit
	gcloud run deploy $(CLOUD_RUN_STREAMLIT_SERVICE) \
		--project $(GCP_PROJECT_ID) \
		--region $(CLOUD_RUN_REGION) \
		--image $(CLOUD_RUN_STREAMLIT_IMAGE_URI) \
		--allow-unauthenticated \
		--min-instances $(CLOUD_RUN_STREAMLIT_MIN_INSTANCES) \
		--max-instances $(CLOUD_RUN_STREAMLIT_MAX_INSTANCES) \
		--concurrency $(CLOUD_RUN_STREAMLIT_CONCURRENCY) \
		--cpu $(CLOUD_RUN_STREAMLIT_CPU) \
		--memory $(CLOUD_RUN_STREAMLIT_MEMORY) \
		--execution-environment gen2 \
		--service-account $(CLOUD_RUN_STREAMLIT_SA) \
		--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID) \
		--set-env-vars GCS_BUCKET=$(GCS_BUCKET) \
		--set-env-vars SYNC_STATE_GCS_BUCKET=$(GCS_BUCKET) \
		--set-env-vars SYNC_STATE_GCS_BLOB=state/sync_state.json \
		--set-env-vars DUCKDB_GCS_BLOB=$(CLOUD_RUN_DUCKDB_BLOB) \
		--set-env-vars DUCKDB_PATH=/app/data/warehouse.duckdb \
		--set-env-vars DUCKDB_COPY_LOCAL=0 \
		--set-env-vars GCS_MOUNT_ROOT=/mnt/gcs \
		--set-env-vars ENGINE=duckdb \
		--set-env-vars LLM_PROVIDER=$(LLM_PROVIDER) \
		--set-env-vars GEMINI_MODEL=$(GEMINI_MODEL) \
		$(CLOUD_RUN_STREAMLIT_GEMINI_FLAG) \
		--set-env-vars MAX_BYTES_BILLED=$(MAX_BYTES_BILLED) \
		--set-env-vars APP_BRAND_NAME="WhyLine Denver" \
		--add-volume=name=duckdb-bucket,type=cloud-storage,bucket=$(GCS_BUCKET) \
		--add-volume-mount=volume=duckdb-bucket,mount-path=/mnt/gcs

ci-help:
	@echo "Targets: install | lint | format | test | run | ingest-* | bq-load(-local|-realtime|-historical) | dbt-* | dev-loop | export-diagrams | cloud-run-(build|push|deploy-streamlit) | streamlit-(build|run)"

.SHELLFLAGS := -o pipefail -c
SHELL := /bin/bash
