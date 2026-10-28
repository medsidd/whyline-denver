# What is WhyLine Denver?

WhyLine Denver helps people investigate Denver-area transit reliability and where service problems overlap with safety, access, and economic vulnerability. It combines public RTD feeds, crash and sidewalk records, weather observations, and Census data in a [web dashboard](https://www.whylinedenver.com/app).

## What you can investigate

| Area | Questions the data can support |
|---|---|
| Reliability | Which sampled routes/stops have lower on-time shares or inconsistent vehicle spacing? |
| Safety | Which stops are near more recorded traffic crashes? |
| Equity | Where do reliability problems overlap with nearby populations that rely on transit? |
| Access | Which stops have less recorded sidewalk length nearby? |

Ask a question in plain English, review the generated SQL, and run it. Results can appear as a table, chart, or map; CSV and warehouse downloads support further analysis. Ready-made questions bypass AI generation.

The intended audiences include planners, advocates, journalists, and people interested in their neighborhood's transit. The project is independently maintained and is not an official RTD or City of Denver service.

## What a result means

Reliability is calculated from sampled/resolved feed observations, not every scheduled arrival. The implementation can treat missing delay as zero, which can make on-time rates look better. Nearby sidewalk length is not a verified accessible route, and a crash count near a stop does not establish transit caused those crashes.

Census indicators describe areas, not individual riders. Priority scores combine chosen weights and incomplete coverage; they are a screening tool rather than an official investment ranking. Read [metric definitions](METRICS_GLOSSARY.md) and [coverage](DATA_SOURCES.md) before drawing conclusions.

## Freshness and limits

Realtime capture/load schedules were verified at 15-minute intervals on October 26, 2026. The public API defaults to a nightly DuckDB snapshot, so fresh realtime collection does not mean equally fresh dashboard results. Weather can arrive late; missing observations remain unknown. Census vintage is configured to 2023 and does not advance just because the collection job runs nightly.

This is an analysis platform, not a trip planner or live arrival service. It does not include passenger counts, fares, crowding, or service alerts. Start with [how it works](HOW_IT_WORKS.md), [use cases](USE_CASES.md), or the [FAQ](FAQ.md).
