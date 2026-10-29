# Documentation

Start with the [project README](../README.md). Current implementation guides live under `technical/`; public explanations live under `public/`. Dated observations are explicitly separated from configuration and historical engineering lessons.

## Public explanations

| Document | Purpose |
|---|---|
| [Overview](public/OVERVIEW.md) | Product purpose, audience, and limits |
| [How it works](public/HOW_IT_WORKS.md) | Question-to-answer workflow and data processing |
| [Data sources](public/DATA_SOURCES.md) | Seven ingestors, geography, vintages, and coverage gaps |
| [Metrics glossary](public/METRICS_GLOSSARY.md) | Actual metric definitions and interpretation caveats |
| [Use cases](public/USE_CASES.md) | Questions the available data can help investigate |
| [FAQ](public/FAQ.md) | Freshness, privacy behavior, exports, and common limitations |

## Build and operate

| Document | Purpose |
|---|---|
| [Architecture](technical/ARCHITECTURE.md) | Canonical system design and design rationale |
| [Development](technical/DEVELOPMENT.md) | Local setup, settings, artifacts, and command side effects |
| [Data pipeline](technical/DATA_PIPELINE.md) | Ingestion, loading, dbt, exports, and DuckDB refresh |
| [API reference](technical/API_REFERENCE.md) | Endpoint inventory, models, limits, and errors |
| [Frontend](technical/FRONTEND.md) | Component map, persistence, API proxy, and visualization behavior |
| [Testing](technical/TESTING.md) | Existing offline tests, cloud checks, CI, and coverage gaps |
| [GitHub workflows](../.github/workflows/README.md) | Actual triggers, recipe selections, secrets, artifacts, and sequencing |
| [Deployment](technical/DEPLOYMENT.md) | API, realtime image, frontend, and workflow deployment |
| [Operations and costs](technical/OPERATIONS.md) | Dated live status, billing snapshot, and refresh procedures |
| [QA validation](QA_Validation_Guide.md) | Check each processing and serving layer without treating one green signal as complete health |
| [Current diagrams](diagrams/README.md) | Pipeline, query flow, and complete SQL lineage in Mermaid |
| [Model reference](../dbt/models/README.md) | Complete SQL-model inventory and links to definitions |
| [Data contracts](contracts/CONTRACTS.md) | Raw output schema sources, loader registration, and versioning |
| [Naming and time](guides/BQ_Naming_and_Time.md) | Actual dataset names, raw metadata, and Denver time handling |
| [Realtime strategy](guides/GTFS_RT_Strategy.md) | Continuous capture, stop visits, and measurement limitations |
| [Realtime stop visits plan](technical/plans/realtime-stop-visits.md) | Approved design, discovery evidence, costs, and owner runbook for continuous capture and `fct_stop_visit` |
| [Weather strategy](guides/NOAA_Data_Collection_Strategy.md) | Rolling collection, unknown weather, and late corrections |

## Extension guides

- [Add a source](technical/guides/ADDING_A_DATA_SOURCE.md).
- [Add a mart](technical/guides/ADDING_A_MART.md).
- [Adapt another city](technical/guides/ADAPTING_TO_OTHER_CITIES.md).
- [Realtime container reference](../infra/cloud-run/README.md).

## Engineering history worth retaining

- [BigQuery optimization](case-studies/bigquery-cost-optimization-2025.md): deduplication, partition pruning, materialization, and frequency tradeoffs. Historical projections are not today's bill.
- [October 2026 recovery](case-studies/pipeline-recovery-2026.md): Census, route aggregation, weather semantics, exports, offline CI, and deployment lessons.

The duplicated architecture document, superseded pause handoff, redundant cost report, and session-by-session recovery reports were consolidated into these references. Git history retains tracked older versions. Agent sessions start with [AGENTS.md](../AGENTS.md); [Codex context](codex/README.md) links to the same shared authority.
