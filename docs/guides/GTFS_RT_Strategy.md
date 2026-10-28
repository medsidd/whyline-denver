# GTFS realtime sampling strategy

WhyLine Denver samples RTD Trip Updates and Vehicle Positions to retain observations that would otherwise disappear from the live feed. These are estimates/snapshots, not a census of completed arrivals.

## Actual collection path

Cloud Scheduler invokes `realtime-ingest`, which runs `whyline.ingest.gtfs_realtime` and writes a manifest plus two compressed CSVs under `raw/rtd_gtfsrt/snapshot_at=…/`. The verified October 26, 2026 cadence is every 15 minutes, 24 hours per day: 96 nominal invocations per full day. Cloud Run defaults to one snapshot per invocation. The local `make ingest-gtfs-rt` target intentionally takes two snapshots 90 seconds apart.

The offset `realtime-load` schedule runs at minutes 2, 17, 32, and 47. It loads new registered raw files, runs the realtime dbt subset, and updates BigQuery freshness. The two realtime GitHub workflow files are manual fallbacks. There is no recurring three-snapshot GitHub capture chain or 30-minute handoff delay.

See [container reference](../../infra/cloud-run/README.md) and [operations](../technical/OPERATIONS.md) for configuration and live checks. The nightly export/DuckDB cycle is separate, so the public default engine can lag realtime BigQuery.

## Feed addresses

The source defaults still use `https://www.rtd-denver.com/files/gtfs-rt/TripUpdate.pb` and `VehiclePosition.pb`. On October 26, 2026, read-only requests followed redirects and returned protobuf responses at the newer canonical endpoints:

- `https://open-data.rtd-denver.com/files/gtfs-rt/rtd/TripUpdate.pb`
- `https://open-data.rtd-denver.com/files/gtfs-rt/rtd/VehiclePosition.pb`

[RTD's current feed page](https://www.rtd-denver.com/open-records/open-spatial-information/real-time-feeds) documents the canonical addresses and legacy-address deprecation. This documentation update does not change source defaults; continued legacy redirects are an upstream dependency to review in a separate code/deployment change.

## Why sample and retain raw data?

Repeated captures support time-of-day reliability and feed-coverage analysis. Raw retention enables replay and model corrections; MD5 load deduplication avoids loading an identical file repeatedly. More frequent sampling provides finer temporal resolution but increases cloud processing frequency. The current cadence is a cost/freshness tradeoff, not a guarantee of continuous coverage.

## Interpretation limits

- Feed coverage varies by trip, stop, time, and mode; no fixed coverage percentages are established here.
- Staging selects one row per `(feed_ts_utc, trip_id)`, not every stop update from every trip. Repeated raw rows are therefore not equivalent to independent arrivals.
- Delay values can be predictions, derived timestamps, or unavailable. Downstream resolution can default missing delay to zero; inspect `n_reported_events` alongside `n_events` where available.
- Nearby vehicle positions do not prove an arrival occurred at a particular stop.
- Source feed timestamps, invocation times, and event times differ. Many legitimate rows share one timestamp; a row count above a threshold does not establish duplication.
- Bounding-box and delay-range checks are quality signals. Inspect parser/manifest behavior before assuming every flagged record is filtered out.

Do not use historical annual volume/cost estimates as current measurements. Current spend is in [operations](../technical/OPERATIONS.md); metric definitions are in [the glossary](../public/METRICS_GLOSSARY.md).

## Validate

Check both job executions, recent GCS objects, raw timestamp coverage, staging grain, mart dates/counts, and served results. Investigate gaps against the actual 15-minute cadence and elapsed portion of the day rather than the old 45/288-snapshot targets. [QA validation](../QA_Validation_Guide.md) has bounded queries and a layer-by-layer checklist.
