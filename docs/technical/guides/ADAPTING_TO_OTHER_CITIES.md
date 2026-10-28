# Adapt the project to another city

The warehouse/API/dashboard pattern is reusable, but this checkout is Denver-specific and is not a configuration-only multi-city system. Treat adaptation as a fork with source, model, geography, infrastructure, and UI validation.

## Review surface

| Area | Actual locations and work |
|---|---|
| Static transit | `ingest/gtfs_static.py::DEFAULT_GTFS_URL`; inspect feed tables/calendar semantics and IDs |
| Realtime transit | `gtfs_realtime.py` feed defaults and `DENVER_*` bounding-box constants; inspect authentication, coverage, event-time interpretation |
| Crashes / sidewalks | Denver ArcGIS defaults, field mappings, severity rules, projections, validation bounds; a different portal often needs a new/changed parser |
| Weather | `noaa_daily.py::DEFAULT_STATION`, CLI station, and `dbt/dbt_project.yml::weather_station`; verify actual metric/date coverage before choosing a station |
| Census | ACS CLI `--state-fips`, `--county-fips`, vintage/variable configuration in `acs_variables.yml`; tract CLI geography and geometry source |
| Time | `America/Denver` in models/macros/API/frontend formatting, UTC loader windows, GTFS times beyond 24:00 and operational service dates |
| Geometry | WGS84 outputs, local projected length calculations, county boundaries, stop buffers, reference geometry validity |
| Cloud | Project/bucket/datasets, dbt profiles/macros, images, identities, secrets, scheduler/workflows, billing export, frontend proxy/domain |
| Presentation | Frontend metadata, copy, assets, source attribution, fonts/tokens, model/metric labels; unused `APP_*` template values are not dynamic Next.js branding |

Search before changing:

```bash
rg -n 'America/Denver|whyline-denver|whylinedenver|DENVER_|08031|USW00003017' src api dbt frontend Makefile infra .github
```

Exclude generated/build/dependency output when reviewing results. Do not globally replace every match: historical examples, tests, model names, public identifiers, and credentials have different roles.

## Validate assumptions

The current reliability model selects one row per trip/snapshot and can default missing delay to zero. Confirm those choices fit the new feed before reusing performance claims. Schedule expansion uses the latest feed rather than historical version matching. County-level ACS coverage and sidewalk inventories may not align with a regional transit network.

Buffers, weights, precipitation thresholds, and population weighting are modeling choices, not universal standards. Validate both source distributions and analytical meaning; changing a city URL alone does not establish correct metrics.

## Safe build path

Start with recorded fixtures and offline tests. Fetch small local source samples and inspect contracts. Use explicit registered schemas and new cloud resources for the fork; do not point adapted commands at Denver's retained datasets. Any cloud loading/build/export/deployment is a separate operational step.

Build the required dbt ancestors, run data assertions, export/refresh DuckDB, generate matching artifacts, then verify API models, representative SQL, maps, labels, and downloads. Read [source](ADDING_A_DATA_SOURCE.md) and [mart](ADDING_A_MART.md) extension guides for registrations. No shared multi-city selector, per-city routing, or automatic time/geography abstraction is implemented.
