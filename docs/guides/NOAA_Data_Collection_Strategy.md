# NOAA weather collection and late corrections

## Source and publication

`src/whyline/ingest/noaa_daily.py` collects GHCND `PRCP`, `SNOW`, `TMIN`, `TMAX`, and `TAVG` through NOAA CDO. The configured default is Denver International Airport, `USW00003017`, matching `dbt/dbt_project.yml::weather_station`. CDO requests use metric units; code interprets mm/Celsius directly. A local fallback CSV must use compatible metric data.

The nightly Makefile target collects a rolling 30-day UTC interval through yesterday. NOAA observations may arrive late, vary by metric, or be absent for a station; no fixed completion delay or completeness percentage is guaranteed. Check actual station/date/metric coverage before changing a station or declaring a pipeline failure.

An extract with all precipitation missing fails before writing the output/manifest. Partially missing windows are retained with nulls. New files use `raw/noaa_daily/extract_date=…/station=…/weather.csv.gz`; older files without the station directory remain supported by the loader. An existing same-extract-date/station output is skipped, so a same-day rerun is not automatically a fresh correction.

## Versioning and staging

Each new extract date creates another source version. MD5-identical files can be skipped by the loader; raw records are not guaranteed to append on every invocation. `stg_weather` chooses the newest `_ingested_at` record per `(date, station)`. A newer null is not replaced by an older non-null automatically.

`fct_weather_daily` keeps every station; route-day reliability selects the configured station. Route-day reliability labels missing precipitation `unknown` and leaves unavailable snow nullable. `mart_weather_impacts` excludes unknown days and computes its dry-day baseline within the configured 30-day window. If there is no observed overlap, comparisons may be empty; without dry days, the baseline/delta can be null.

## Propagating corrections

Late weather data must pass through every layer: new source extract → raw load → staging → route-day rebuild → weather comparison → export → DuckDB refresh → served query. Rebuilding only the BigQuery table is insufficient.

Route-day incremental rebuilding uses the weather lookback. Export logic detects older rebuilt partitions using `build_run_at`, not only a newest-date checkpoint. A deliberate bounded repair can force selected exports after verifying model rebuilds; see [pipeline](../technical/DATA_PIPELINE.md). Historical corrections outside current lookbacks need an explicit selection/full-refresh plan and cloud authorization.

## Diagnose without inventing weather

1. Inspect the request station/date range, token binding, response, and manifest missing rates.
2. Compare raw versions with the latest staging record for the same date/station.
3. Check configured station agreement between ingestion and dbt.
4. Inspect route-day `unknown` counts and weather comparison baselines.
5. Verify changed historical partitions were exported and loaded into the served warehouse.

Never convert unavailable precipitation to a dry observation or infer units from value size. The [October recovery case study](../case-studies/pipeline-recovery-2026.md) explains why these rules exist; [QA validation](../QA_Validation_Guide.md) includes current completeness queries.
