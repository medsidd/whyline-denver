.PHONY: install lint format test test-ingest run demo ingest-all ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs bq-load bq-load-local dbt-source-freshness ci-help

PY=python
PIP=pip

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	pre-commit install

GCS_BUCKET ?= whylinedenver-raw

lint:
	ruff check . && black --check .

format:
	ruff check . --fix && black .

test:
	pytest

test-ingest:
	pytest -k ingest

run:
	streamlit run app/streamlit_app.py

demo:
	DBT_PROFILES_DIR=$$PWD/dbt/profiles python -m scripts.dbt_with_env deps --project-dir dbt --no-use-colors || true
	DBT_PROFILES_DIR=$$PWD/dbt/profiles python -m scripts.dbt_with_env parse --project-dir dbt --no-use-colors --target demo
	DBT_PROFILES_DIR=$$PWD/dbt/profiles python -m scripts.dbt_with_env docs generate --project-dir dbt --no-use-colors --target demo

ingest-all:
	python -m whylinedenver.ingest.gtfs_static --local
	python -m whylinedenver.ingest.gtfs_realtime --local --snapshots 2 --interval-sec 10
	python -m whylinedenver.ingest.denver_crashes --local
	python -m whylinedenver.ingest.denver_sidewalks --local
	python -m whylinedenver.ingest.noaa_daily --local --start 2024-10-01 --end 2024-10-31
	python -m whylinedenver.ingest.acs --local --year 2023 --geo tract

ingest-gtfs-static:
	python -m whylinedenver.ingest.gtfs_static --local

ingest-gtfs-rt:
	python -m whylinedenver.ingest.gtfs_realtime --local --snapshots 3 --interval-sec 60

ingest-crashes:
	python -m whylinedenver.ingest.denver_crashes --local

ingest-sidewalks:
	python -m whylinedenver.ingest.denver_sidewalks --local

ingest-noaa:
	python -m whylinedenver.ingest.noaa_daily --local --start 2025-10-01 --end 2025-10-12

ingest-acs:
	python -m whylinedenver.ingest.acs --local --year 2023 --geo tract

bq-load:
	python -m load.bq_load --src gcs --bucket $(GCS_BUCKET) --since 2025-01-01

bq-load-local:
	python -m load.bq_load --src local --bucket $(GCS_BUCKET) --since 2025-01-01

dbt-source-freshness:
	DBT_PROFILES_DIR=$$PWD/dbt/profiles python -m scripts.dbt_with_env source freshness --project-dir dbt --target prod --select source:raw


ci-help:
	@echo "Targets: install | lint | format | test | run | demo"
