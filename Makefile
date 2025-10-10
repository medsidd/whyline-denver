.PHONY: install lint format test run demo ci-help

PY=python
PIP=pip

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	pre-commit install

lint:
	ruff check . && black --check .

format:
	black .

test:
	pytest

run:
	streamlit run app/streamlit_app.py

demo:
# minimal dbt compile/docs on demo target
	cd dbt && dbt --no-use-colors deps || true
	cd dbt && dbt --no-use-colors parse --target demo
	cd dbt && dbt --no-use-colors docs generate --target demo

ci-help:
	@echo "Targets: install | lint | format | test | run | demo"


