# From public data to an answer

## 1. Collect source observations

Seven collection programs fetch RTD schedules and sampled realtime updates, Denver crash and sidewalk data, NOAA daily weather, ACS demographic estimates, and Census tract geometry. Extracts and manifests are retained so records can be traced to their source.

The realtime jobs were verified to run every 15 minutes on October 26, 2026. Nightly jobs refresh other extracts, but the underlying source may be older: fetching 2023 Census estimates again does not make them 2026 estimates.

## 2. Build analysis tables

The loader writes explicit raw schemas into BigQuery and tracks identical files to avoid redundant loads. dbt SQL models clean and join the sources into nine tables: reliability by route/day and stop/hour, weather comparisons, crash proximity, sidewalk access, vulnerability, priority hotspots, plus stop and route reference tables.

Source geometry and demographic indicators provide context for transit stops. Those joins do not establish an individual's experience or a causal relationship. [The glossary](METRICS_GLOSSARY.md) explains the formulas and limitations.

## 3. Publish a queryable snapshot

The cloud tables are exported to Parquet and copied into a DuckDB database. The dashboard can query either engine; its default is DuckDB. That snapshot is usually refreshed by the nightly workflow and can be older than BigQuery's realtime updates.

Missing weather stays unknown and is excluded from weather comparisons. Late observations can update older tables and exports; freshness must be checked alongside actual date coverage.

## 4. Ask, inspect, and run

Enter a question or load a ready-made query. With Gemini configured, your question, filters, and schema information are sent to the provider to generate SQL. The SQL is shown before execution and checked on the server. You can edit it; check that the intended date, route, and weather conditions appear in the query.

Ready-made questions avoid AI generation. One weather card currently refers to snow even though its SQL selects moderate/heavy precipitation; that is not a snow-only result.

## 5. Interpret and export

The results view shows a table and, when columns match supported patterns, a chart or map. Query-result CSVs contain displayed results. Separate controls export seven analytic tables as CSV or download the DuckDB warehouse; Parquet is an internal pipeline format.

Before sharing a result, record the engine, dates, source coverage, metric definition, and SQL. Avoid calling a sampled on-time share a complete arrival rate, a sidewalk score an accessibility audit, or a weather association proof of causation.

See [data sources](DATA_SOURCES.md), [FAQ](FAQ.md), and [operations](../technical/OPERATIONS.md).
