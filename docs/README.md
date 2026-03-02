# WhyLine Denver — Documentation

This directory contains all documentation for the WhyLine Denver project. Documents are organized into two audiences: technical (developers and contributors) and public (transit planners, riders, and the general public).

---

## For Transit Planners, Riders, and the Public

Start here if you want to understand what WhyLine Denver is, what data it uses, and how to get answers from it.

| Document | Description |
|----------|-------------|
| [OVERVIEW.md](public/OVERVIEW.md) | What WhyLine Denver is and who it's for, in plain English |
| [HOW_IT_WORKS.md](public/HOW_IT_WORKS.md) | How data flows from a bus stop to a dashboard answer, step by step |
| [DATA_SOURCES.md](public/DATA_SOURCES.md) | Where each data source comes from, how often it updates, and what it doesn't cover |
| [METRICS_GLOSSARY.md](public/METRICS_GLOSSARY.md) | Plain-English definitions of every metric used in the dashboard |
| [USE_CASES.md](public/USE_CASES.md) | Concrete examples: how transit planners, council members, journalists, and riders use the dashboard |
| [FAQ.md](public/FAQ.md) | Common questions answered without technical jargon |

---

## For Developers and Contributors

Start here if you're setting up the project, contributing code, or building on the data pipeline.

### Core Documentation

| Document | Description |
|----------|-------------|
| [technical/ARCHITECTURE.md](technical/ARCHITECTURE.md) | System design: data flow, dual-engine pattern, infrastructure, cost model, and technology choices |
| [technical/DATA_PIPELINE.md](technical/DATA_PIPELINE.md) | Complete pipeline walkthrough: all 7 ingestors, BigQuery loading, dbt models, and DuckDB sync |
| [technical/API_REFERENCE.md](technical/API_REFERENCE.md) | Every FastAPI endpoint with request/response examples, SQL generation flow, and guardrail rules |
| [technical/FRONTEND.md](technical/FRONTEND.md) | Next.js component tree, Zustand state shape, chart auto-detection logic, and API integration |
| [technical/DEVELOPMENT.md](technical/DEVELOPMENT.md) | Local setup, all environment variables, make targets, pre-commit hooks, and common errors |
| [technical/DEPLOYMENT.md](technical/DEPLOYMENT.md) | Cloud Run jobs and services, Vercel, GitHub Actions secrets, and Cloud Scheduler setup |
| [technical/TESTING.md](technical/TESTING.md) | pytest suite, dbt data quality tests, CI pipeline, and how to add new tests |

### How-To Guides

| Document | Description |
|----------|-------------|
| [technical/guides/ADDING_A_DATA_SOURCE.md](technical/guides/ADDING_A_DATA_SOURCE.md) | Step-by-step guide to adding an 8th ingestor |
| [technical/guides/ADDING_A_MART.md](technical/guides/ADDING_A_MART.md) | How to add a new dbt mart table, including materialization choice and DuckDB registration |
| [technical/guides/ADAPTING_TO_OTHER_CITIES.md](technical/guides/ADAPTING_TO_OTHER_CITIES.md) | How to adapt WhyLine Denver for a different city's transit system |

### Model Reference

| Document | Description |
|----------|-------------|
| [../dbt/models/README.md](../dbt/models/README.md) | All 25 dbt models documented: schema, materialization, tests, and incremental logic |
| [Interactive dbt docs](https://medsidd.github.io/whyline-denver/) | Auto-generated model lineage, column docs, and data quality test results |

### Additional References

| Document | Description |
|----------|-------------|
| [QA_Validation_Guide.md](QA_Validation_Guide.md) | Pipeline health check procedures and how to diagnose data quality issues |
| [contracts/CONTRACTS.md](contracts/CONTRACTS.md) | Data contracts: expected schemas for each raw ingestion output |
| [COST_OPTIMIZATION_DEC_2025.md](COST_OPTIMIZATION_DEC_2025.md) | History of BigQuery cost optimization through three phases (Dec 2025) |

---

## Finding the Right Document

**"I want to run this locally"** → [DEVELOPMENT.md](technical/DEVELOPMENT.md)

**"I want to understand what the mart tables contain"** → [DATA_PIPELINE.md](technical/DATA_PIPELINE.md) + [dbt/models/README.md](../dbt/models/README.md)

**"I want to call the API directly"** → [API_REFERENCE.md](technical/API_REFERENCE.md)

**"I want to add a new data source"** → [ADDING_A_DATA_SOURCE.md](technical/guides/ADDING_A_DATA_SOURCE.md)

**"I want to adapt this for my city"** → [ADAPTING_TO_OTHER_CITIES.md](technical/guides/ADAPTING_TO_OTHER_CITIES.md)

**"I want to understand what 'vulnerability score' means"** → [METRICS_GLOSSARY.md](public/METRICS_GLOSSARY.md)

**"I want to show this to a city council member"** → [OVERVIEW.md](public/OVERVIEW.md) + [USE_CASES.md](public/USE_CASES.md)

**"Something is broken"** → [QA_Validation_Guide.md](QA_Validation_Guide.md) + [TESTING.md](technical/TESTING.md)
