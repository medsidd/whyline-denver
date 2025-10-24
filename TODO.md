# WhyLine Denver — TODO Backlog

---

## Phase 2 — Ingestion tasks (one per dataset)

- [ ] **Common ingestion utils** — Implement shared storage, manifest, and validation helpers used by all ingestors.  
  _Owner: @owner • Labels: phase:2, area:ingest, type:infra_

- [ ] **GTFS static ingestor** — Download ZIP, explode TXT files as-is, validate required files, and write partitioned artifacts.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:gtfs-static, type:feature_

- [ ] **GTFS-Realtime snapshotter** — Poll Trip Updates & Vehicle Positions every N minutes, convert to tidy CSV, and dedupe snapshots.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:gtfs-rt, type:feature_

- [ ] **Denver crashes exporter** — Pull 5y+YTD via ArcGIS, normalize columns, convert times to UTC and coords to EPSG:4326.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:crashes, type:feature_

- [ ] **Denver sidewalks exporter** — Export sidewalk features, compute length (m) and centroid, and write CSV.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:sidewalks, type:feature_

- [ ] **NOAA daily weather ingestor** — Fetch daily summaries for station USW00023062, normalize units, and derive bins.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:weather, type:feature_

- [ ] **ACS tract ingestor** — Fetch ACS 5-year variables for Denver tracts and compute vulnerability percentages.  
  _Owner: @owner • Labels: phase:2, area:ingest, dataset:acs, type:feature_

- [ ] **Make targets for ingestion** — Add `make ingest-*` and `make ingest-all` with MODE/GCS parameters.  
  _Owner: @owner • Labels: phase:2, area:tooling, type:chore_

- [ ] **Ingestion tests & fixtures** — Add unit tests and small fixtures per dataset with manifest assertions.  
  _Owner: @owner • Labels: phase:2, area:testing, type:test_

---

## Phase 3 — Load tasks (files → BigQuery raw)

- [ ] **Parametric loader** — Map raw CSV/TXT to BQ tables with schemas, meta columns, and idempotent runs.  
  _Owner: @owner • Labels: phase:3, area:load, type:feature_

- [ ] **Schema definitions** — Define column types for GTFS/GTFS-RT/Crashes/Sidewalks/Weather/ACS with UTC timestamps.  
  _Owner: @owner • Labels: phase:3, area:load, type:spec_

- [ ] **Partitioning strategy** — Partition large facts (GTFS-RT, crashes) by date and cluster where useful.  
  _Owner: @owner • Labels: phase:3, area:performance, type:design_

- [ ] **Make target `bq-load`** — Add make target to run all raw loads idempotently.  
  _Owner: @owner • Labels: phase:3, area:tooling, type:chore_

---

## Phase 4 — dbt models (one per model)

- [ ] **Sources & freshness** — Declare sources for all raw tables with sensible freshness checks.  
  _Owner: @owner • Labels: phase:4, area:dbt, type:spec_

- [ ] **stg_gtfs_routes** — Normalize routes and expose key columns.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_gtfs_routes, type:feature_

- [ ] **stg_gtfs_stops** — Normalize stops with POINT geometry.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_gtfs_stops, type:feature_

- [ ] **stg_gtfs_trips** — Normalize trips with service day derivation.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_gtfs_trips, type:feature_

- [ ] **stg_gtfs_stop_times** — Expand stop times with hour buckets.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_gtfs_stop_times, type:feature_

- [ ] **stg_rt_events** — Flatten GTFS-RT snapshots to a tidy fact with delays and event timestamps.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_rt_events, type:feature_

- [ ] **stg_crashes** — Standardize crash severity and geometry.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_crashes, type:feature_

- [ ] **stg_sidewalks** — Aggregate sidewalk lengths and attributes.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_sidewalks, type:feature_

- [ ] **stg_weather** — Normalize daily weather and derive bins (snow/precip).  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_weather, type:feature_

- [ ] **stg_acs_geo** — Prepare ACS tract metrics with derived percentages.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:stg_acs_geo, type:feature_

- [ ] **mart_reliability_by_route_day** — Aggregate on-time metrics by route × service day × weather bin.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_reliability_by_route_day, type:feature_

- [ ] **mart_reliability_by_stop_hour** — Compute mean delay and headway adherence by stop × hour.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_reliability_by_stop_hour, type:feature_

- [ ] **mart_crash_proximity_by_stop** — Count crashes within 100m/250m windows near stops.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_crash_proximity_by_stop, type:feature_

- [ ] **mart_access_score_by_stop** — Score sidewalk density/presence in 200m buffers.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_access_score_by_stop, type:feature_

- [ ] **mart_vulnerability_by_stop** — Join stops to nearby tracts and compute composite vulnerability.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_vulnerability_by_stop, type:feature_

- [ ] **mart_priority_hotspots** — Rank stops where vulnerability, low reliability, and crash exposure overlap.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_priority_hotspots, type:feature_

- [ ] **mart_weather_impacts** — Measure reliability deltas on snow/precip days vs normal.  
  _Owner: @owner • Labels: phase:4, area:dbt, model:mart_weather_impacts, type:feature_

- [ ] **dbt tests & docs** — Add not_null/unique/relationships tests and column descriptions.  
  _Owner: @owner • Labels: phase:4, area:dbt, type:test_

- [ ] **Allow-list for app** — Add `meta.allow_in_app: true` to app-queryable marts and define exposures.  
  _Owner: @owner • Labels: phase:4, area:dbt, type:spec_

---

## Phase 5 — Sync tasks (BQ → Parquet → DuckDB)

- [ ] **Export BQ marts to Parquet** — Implement partition-aware export script writing to GCS under `marts/<mart>/run_date=...`.  
  _Owner: @owner • Labels: phase:5, area:sync, type:feature_

- [ ] **DuckDB refresh** — Implement Parquet import and optional materialization into DuckDB tables.  
  _Owner: @owner • Labels: phase:5, area:sync, type:feature_

- [ ] **State/control tracking** — Record last processed partitions and ensure idempotency.  
  _Owner: @owner • Labels: phase:5, area:sync, type:infra_

- [ ] **Make target `sync-duckdb`** — Wire export + refresh into a single command.  
  _Owner: @owner • Labels: phase:5, area:tooling, type:chore_

---

## Phase 6 — App components

- [ ] **Streamlit shell** — Build UI with query box, engine switch, filters, and freshness badges.  
  _Owner: @owner • Labels: phase:6, area:app, type:feature_

- [ ] **DuckDB engine** — Implement `execute(sql)` and basic stats return.  
  _Owner: @owner • Labels: phase:6, area:app, type:feature_

- [ ] **BigQuery engine** — Implement dry-run bytes check, `MAX_BYTES_BILLED`, and query execution.  
  _Owner: @owner • Labels: phase:6, area:app, type:feature_

- [ ] **dbt artifacts loader** — Load manifest/catalog and surface allow-listed models + column docs.  
  _Owner: @owner • Labels: phase:6, area:app, type:feature_

- [ ] **SQL guardrails** — Enforce SELECT-only, deny DDL/DML, and restrict to allowed models.  
  _Owner: @owner • Labels: phase:6, area:app, type:security_

- [ ] **LLM module** — Prompt assembly, provider call, SQL + short explanation return.  
  _Owner: @owner • Labels: phase:6, area:app, type:feature_

- [ ] **Telemetry & caching** — Log query stats and add small TTL cache for repeated queries.  
  _Owner: @owner • Labels: phase:6, area:app, type:perf_

---

## Phase 7 — CI schedules

- [ ] **PR CI** — Lint, tests, dbt parse/docs for `prod` target.  
  _Owner: @owner • Labels: phase:7, area:ci, type:chore_

- [ ] **Nightly BigQuery build** — `dbt run/test --target prod` + publish docs artifacts + export Parquet.  
  _Owner: @owner • Labels: phase:7, area:ci, type:automation_

- [ ] **Nightly DuckDB refresh** — Refresh local DuckDB from GCS Parquet and publish artifact.  
  _Owner: @owner • Labels: phase:7, area:ci, type:automation_

- [ ] **Status badges** — Add CI/nightly badges to README.  
  _Owner: @owner • Labels: phase:7, area:docs, type:chore_

---

## Phase 8 — Docs

- [ ] **README** — Add value prop, quickstart (DuckDB), prod path (BQ), freshness explainer, and attributions.  
  _Owner: @owner • Labels: phase:8, area:docs, type:docs_

- [ ] **dbt docs hosting** — Publish to GitHub Pages and link from app.  
  _Owner: @owner • Labels: phase:8, area:docs, type:automation_

- [ ] **Architecture diagrams** — Add pipeline and app/allow-list diagrams.  
  _Owner: @owner • Labels: phase:8, area:docs, type:design_

- [ ] **FAQ** — Document “Why DuckDB?”, guardrails, and licensing approach.  
  _Owner: @owner • Labels: phase:8, area:docs, type:docs_

---

## Phase 9 — Hosting

- [ ] **App deploy** — Deploy Streamlit to Hugging Face Spaces with secrets for optional BQ engine.  
  _Owner: @owner • Labels: phase:9, area:hosting, type:deploy_

- [ ] **Custom domain** — Point domain to Space and proxy via Cloudflare for TLS.  
  _Owner: @owner • Labels: phase:9, area:hosting, type:dns_

- [ ] **Docs hosting** — Publish dbt docs to GitHub Pages and verify links.  
  _Owner: @owner • Labels: phase:9, area:hosting, type:deploy_

- [ ] **Uptime check** — Add GitHub Actions health check and badge.  
  _Owner: @owner • Labels: phase:9, area:observability, type:automation_

---

## Phase 10 — UX polish

- [ ] **Prebuilt questions** — Add buttons for key queries (worst routes, crash exposure, snow impacts, equity gaps).  
  _Owner: @owner • Labels: phase:10, area:app, type:feature_

- [ ] **Filters** — Add route/stop/date/weather/timeband filters with sane defaults.  
  _Owner: @owner • Labels: phase:10, area:app, type:feature_

- [ ] **Charts & maps** — Add heatmaps, small multiples by weather bin, and hotspot map with tooltips.  
  _Owner: @owner • Labels: phase:10, area:viz, type:feature_

- [ ] **Exports & badges** — Enable CSV downloads and freshness/build badges.  
  _Owner: @owner • Labels: phase:10, area:app, type:feature_

---

### Definition of Done (for this file)
- `TODO.md` is committed on `main`.  
- Every item has one short sentence and an `_Owner_` placeholder.  
- Headings exist for Phases **2–10** exactly as listed above.
