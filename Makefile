.PHONY: install lint format test test-ingest run demo ingest-all ingest-gtfs-static ingest-gtfs-rt ingest-crashes ingest-sidewalks ingest-noaa ingest-acs ci-help

PY=python
PIP=pip

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	pre-commit install

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
	cd dbt && dbt --no-use-colors deps || true
	cd dbt && DBT_PROFILES_DIR=$$(pwd)/profiles dbt --no-use-colors parse --target demo
	cd dbt && DBT_PROFILES_DIR=$$(pwd)/profiles dbt --no-use-colors docs generate --target demo

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
	python -m whylinedenver.ingest.noaa_daily --local --start 2024-11-01 --end 2024-11-30

ingest-acs:
	python -m whylinedenver.ingest.acs --local --year 2023 --geo tract


ci-help:
	@echo "Targets: install | lint | format | test | run | demo"
