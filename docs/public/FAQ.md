# Frequently asked questions

## How current is the dashboard?

The two reliability tables (route-day and stop-hour) update every 15 minutes; the other tables are rebuilt once a night, around 09:00 UTC, so they run through the previous day. Questions about right now read live views over the 15-minute realtime load, so they trail real time by 15–30 minutes. The downloadable DuckDB warehouse is refreshed nightly. Weather may arrive late. ACS remains the configured 2023 five-year vintage even when re-extracted nightly. Freshness badges are processing timestamps, not guarantees that every source covers that date. See [operations](../technical/OPERATIONS.md) and [sources](DATA_SOURCES.md).

## Why does my route's on-time percentage differ from my experience?

Since October 29, 2026 every stop visit seen in RTD's vehicle reports is timed, and on time means less than a minute early to five minutes late at every stop (RTD's rule; RTD measures only its timepoints, so its own figures run higher). Visits with an unknown delay are left out, and trips that never report go unseen. Before that date, figures come from 15-minute samples with a looser rule. Compare visit counts, dates, and SQL before reading a rate as complete service performance. See [metrics](METRICS_GLOSSARY.md).

## Does it cover buses and rail?

It ingests routes/stops present in RTD's published GTFS feeds, with variable realtime coverage. It does not maintain an authoritative current line list. Equity and city infrastructure data have narrower Denver geography, so regional stops may have incomplete contextual data.

## Why is a value missing, zero, or a weather comparison empty?

Missingness can reflect source coverage, delayed publication, unmatched IDs, artifact/processing issues, or absent baseline observations. Missing weather stays unknown/null. An empty weather result can mean no overlap between observed weather and transit dates; a null delta can mean there were no dry baseline days. A zero access score can reflect incomplete sidewalk inventory. Investigate before replacing nulls or drawing a conclusion.

## Do I need SQL?

No. You can generate SQL from a plain-English question or load a ready-made question, then review and run it. You can edit SQL if comfortable. Ready-made questions use the filters they support and say which ones they used; a filter change reloads one you haven't edited. Filters don't rewrite SQL you've edited, so check the SQL contains the dates and routes you intended. The snow question compares each route's snow days with its other days.

## What is stored or sent when I use it?

No account is required by the current app. Selected question, SQL, explanation, and filters persist in browser localStorage and survive closing the tab; results are not persisted by that store. Clearing site data removes that local state.

With Gemini selected, the question, filters, and schema brief are sent to the provider. Backend caches retain prompts/results temporarily in process memory. Application query logs contain hashes and execution metadata; engine logs may include SQL snippets and operational logs can capture errors. The frontend includes Vercel Analytics and Speed Insights. Retention and provider/hosting settings are not fully specified by this repository; do not treat the app as a place to enter sensitive personal data or assume all state disappears on tab close.

## What can I download?

Displayed query results as CSV (named after your question), any of 18 tables as CSV (using your dates, newest rows first, where a table has a service date), and the DuckDB warehouse binary. Parquet is used internally for synchronization and is not a dashboard/API export option. Limits and date-filter behavior are in [API reference](../technical/API_REFERENCE.md).

## Is this an official RTD or City tool?

No. It is an independent project combining public sources. Public availability does not imply a blanket reuse license; consult each source's terms. The app does not provide trip planning, arrival predictions, passenger counts, fares, or verified accessible walking routes. It can answer questions about right now (which routes are running, how late buses are), but that live data trails real time by 15–30 minutes.

## What does it cost to run?

Google Cloud charges depend on jobs, query scans, storage, traffic, and credits. The October 26 snapshot recorded $7.01 month-to-date after credits and a recent roughly $1.07/day rate; those are dated observations, not a permanent price. BigQuery was the largest component. See [operations](../technical/OPERATIONS.md) for scope, timestamp, exclusions, and a refresh query.

## Can another city use this?

The general architecture can be reused, but it is not a configuration-only multi-city platform. Sources, schemas, geography, time handling, metrics, infrastructure, and UI all need review. See [adaptation guide](../technical/guides/ADAPTING_TO_OTHER_CITIES.md).
