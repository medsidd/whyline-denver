# What is WhyLine Denver?

WhyLine Denver helps people investigate Denver-area transit reliability and where service problems overlap with safety, access, and economic vulnerability. It combines public RTD feeds, crash and sidewalk records, weather observations, and Census data in a [web dashboard](https://www.whylinedenver.com/app).

## What you can investigate

| Area | Questions the data can support |
|---|---|
| Reliability | Which routes and stops are least on time, wait longest, bunch, miss trips, run slowest, crowd, or have the least trustworthy arrival countdown? |
| Weather | How does on-time performance shift on snowy or rainy days? |
| Safety | Which stops are near more recorded traffic crashes, and how walkable is the area around them? |
| Equity and access | Where do reliability problems overlap with nearby populations that rely on transit, and where is sidewalk missing? |
| Right now | Which routes are running, and how late are buses, in data that trails real time by 15–30 minutes? |

Ask a question in plain English, review the generated SQL, and run it. Results can appear as a table, chart, or map (with the routes a result names drawn as lines); CSV and warehouse downloads support further analysis. Ready-made questions bypass AI generation.

The intended audiences include planners, advocates, journalists, and people interested in their neighborhood's transit. The project is independently maintained and is not an official RTD or City of Denver service.

## What a result means

Since October 29, 2026, reliability times every stop visit seen in RTD's vehicle reports, using RTD's on-time rule (less than a minute early to five minutes late); visits with an unknown delay are left out, and trips that never report go unseen. Earlier dates come from 15-minute samples and a looser rule, so don't compare across that date. Nearby sidewalk length is not a verified accessible route, and a crash count near a stop does not establish transit caused those crashes.

Census indicators describe areas, not individual riders. Priority scores combine chosen weights and incomplete coverage; they are a screening tool rather than an official investment ranking. Read [metric definitions](METRICS_GLOSSARY.md) and [coverage](DATA_SOURCES.md) before drawing conclusions.

## Freshness and limits

Most tables are rebuilt nightly; live questions read data loaded every 15 minutes, so they trail real time by 15–30 minutes. The dashboard queries BigQuery; the DuckDB warehouse download is refreshed nightly. Weather can arrive late; missing observations remain unknown. Census vintage is configured to 2023 and does not advance just because the collection job runs nightly.

This is an analysis platform, not a trip planner or arrivals board. It has no passenger counts or fares; crowding comes from the occupancy level some vehicles report, and service alerts are what RTD announced. Start with [how it works](HOW_IT_WORKS.md), [use cases](USE_CASES.md), or the [FAQ](FAQ.md).
