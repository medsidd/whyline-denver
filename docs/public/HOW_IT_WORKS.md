# From public data to an answer

## 1. Collect source observations

Collection programs fetch RTD schedules, Denver crash, sidewalk and street data, NOAA and hourly weather, ACS demographics, Census tract geometry, RTD service alerts, Veo scooter availability, National Transit Database ridership and RTD's own reported on-time figures. A continuous poller reads RTD's realtime feeds every 15 seconds and times each stop visit from vehicle reports. Extracts and manifests are retained so records can be traced to their source.

The poller's results load every 15 minutes. Nightly jobs refresh other extracts, but the underlying source may be older: fetching 2023 Census estimates again does not make them 2026 estimates.

## 2. Build analysis tables

The loader writes explicit raw schemas into BigQuery and tracks identical files to avoid redundant loads. dbt SQL models clean and join the sources into 20 tables the dashboard can query (reliability, waits, missed trips, speeds, crowding, prediction accuracy, weather, crashes, sidewalk access, equity, scheduled service, and stop and route reference tables) and two live views over the newest realtime load.

Source geometry and demographic indicators provide context for transit stops. Those joins do not establish an individual's experience or a causal relationship. [The glossary](METRICS_GLOSSARY.md) explains the formulas and limitations.

## 3. Publish a queryable snapshot

The dashboard queries BigQuery. The 20 tables are also exported to Parquet and copied nightly into a DuckDB database you can download; the live views are not.

Missing weather stays unknown and is excluded from weather comparisons. Late observations can update older tables and exports; freshness must be checked alongside actual date coverage.

## 4. Ask, inspect, and run

Enter a question or load a ready-made query. With Gemini configured, your question, filters, and schema information are sent to the provider to generate SQL. The SQL is shown before execution and checked on the server. You can edit it; check that the intended date, route, and weather conditions appear in the query.

Ready-made questions avoid AI generation. They cover route reliability, crash exposure, snow days, equity gaps, scheduled frequency, arrival-prediction accuracy, missed trips, slow bus segments and the routes running right now. Questions about right now read live views that trail real time by 15–30 minutes; the dashboard says so beside the SQL and the results. Each one uses the filters that fit it (for example your dates and routes for the worst-routes question, the stop ID for crash exposure) and says which ones it didn't use. Reliability questions read only stop-visit dates (from October 29, 2026), because on-time was counted differently before; the snow question compares within each method instead.

## 5. Interpret and export

The results view shows a table and, when columns match supported patterns, a chart or map. Query-result CSVs contain displayed results. Separate controls download any of 18 tables as CSV (by your dates, newest rows first, for tables with a service date) or the DuckDB warehouse; Parquet is an internal pipeline format.

Before sharing a result, record the engine, dates, source coverage, metric definition, and SQL. Avoid calling an on-time share a complete arrival rate (unseen trips are missing), a sidewalk score an accessibility audit, or a weather association proof of causation.

See [data sources](DATA_SOURCES.md), [FAQ](FAQ.md), and [operations](../technical/OPERATIONS.md).
