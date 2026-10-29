# GTFS realtime capture strategy

WhyLine Denver captures RTD Trip Updates and Vehicle Positions continuously and turns them into stop visits: when the vehicle serving a trip reached each stop, with the uncertainty of that time. Before the stop-visit cutover the project sampled both feeds every 15 minutes; those samples are estimates, not a census of completed arrivals.

## Collection path

The stream poller (`whyline.ingest.gtfs_rt_stream`, `JOB_TYPE=stream`) runs on an e2-micro VM. It polls both feeds every 15 seconds with `If-None-Match`, archives every new payload to Coldline (`gs://whylinedenver-rt-archive/rtd_gtfsrt/date=…/HHMM.tar`), and every 15 minutes writes four CSVs under `raw/rtd_gtfsrt_stream/snapshot_at=…/`: trip-update changes, every vehicle report, final stop visits and closed trips. The offset `realtime-load` schedule (minutes 2, 17, 32 and 47) loads them into four raw tables whose partitions expire after 90 days, runs the realtime dbt subset, and updates BigQuery freshness. The [realtime stop visits plan](../technical/plans/realtime-stop-visits.md) has the design, the timing rules and the deploy runbook; [operations](../technical/OPERATIONS.md) has the dated deployment state.

Before the cutover, Cloud Scheduler invoked `realtime-ingest` every 15 minutes (verified October 26, 2026). It runs `whyline.ingest.gtfs_realtime`, which writes a manifest plus two compressed CSVs under `raw/rtd_gtfsrt/snapshot_at=…/`. The cutover checklist pauses it; its raw tables and the legacy models built from them are kept. The local `make ingest-gtfs-rt` target takes two snapshots 90 seconds apart, and the two realtime GitHub workflow files are manual fallbacks for that snapshot path.

See [container reference](../../infra/cloud-run/README.md) for configuration. The nightly export/DuckDB cycle is separate, so the public default engine can lag realtime BigQuery.

## Feed addresses

Both realtime ingestors default to RTD's canonical endpoints:

- `https://open-data.rtd-denver.com/files/gtfs-rt/rtd/TripUpdate.pb`
- `https://open-data.rtd-denver.com/files/gtfs-rt/rtd/VehiclePosition.pb`

The legacy `www.rtd-denver.com/files/gtfs-rt/…` addresses still redirected there on October 26, 2026. [RTD's current feed page](https://www.rtd-denver.com/open-records/open-spatial-information/real-time-feeds) documents the canonical addresses and the legacy deprecation. Static GTFS still uses `www.rtd-denver.com/files/gtfs/google_transit.zip`, which redirects (308, then 307) to `nodejs-prod.rtd-denver.com` and sends no `ETag` or `Last-Modified`, so changes are detected by MD5. All three hosts publish IPv6 addresses (checked October 28, 2026).

## Why keep the raw feed?

The archive keeps every feed payload, so any day can be replayed through the same engine after a fix (`make replay-gtfs-rt`); a replay of the same payloads gives the same visits. The raw stream tables expire after 90 days, while `fct_stop_visit` is permanent and never fully refreshed. MD5 load deduplication avoids loading an identical file twice.

## Interpretation limits

- Coverage varies by trip, stop, time and mode. Check `pct_observed` and `n_reported_events` before comparing groups.
- A visit is an estimate within its own window (`arrival_earliest_ts` to `arrival_latest_ts`). Bus crossings are usually within 30 seconds; rail windows are wider because trains report less often.
- `last_prediction` visits are RTD's final prediction, not an observation. In the October 28, 2026 sample, 2.2% of prediction drops came before the bus arrived, by a median 3 minutes.
- Reports more than 100 m from the route shape (detours, layovers), more than 120 s old, or outside the Denver bounding box are not used. Regional service beyond the box (Nederland, for example) gets fewer crossings.
- The engine times visits from each vehicle's own report timestamp; feed header times only order refreshes. Polling or publishing delays therefore change freshness, not arrival times.
- Partitions before the cutover count one sampled prediction per poll and trip. See [the glossary](../public/METRICS_GLOSSARY.md#legacy-partitions-before-the-cutover).

Do not use historical annual volume/cost estimates as current measurements. Current spend is in [operations](../technical/OPERATIONS.md); metric definitions are in [the glossary](../public/METRICS_GLOSSARY.md).

## Validate

Check the poller heartbeat, archive objects, four stream batches an hour in the raw tables, fact grain, method mix, mart dates/counts and served results. Investigate gaps against the 15-minute batch cadence and the elapsed portion of the day. [QA validation](../QA_Validation_Guide.md) has bounded queries and a layer-by-layer checklist.
