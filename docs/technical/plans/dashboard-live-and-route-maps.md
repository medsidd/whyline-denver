# Dashboard: live questions, route maps and polish

**Status:** active. PR A (polish, topics, site map) merged ([#132](https://github.com/medsidd/whyline-denver/pull/132)); PR B (route maps) in review; PR C (live questions) follows.

## Owner requests and decisions (November 9, 2026)

- Add a readable **site map** page and link it from the footer, alongside `sitemap.xml`.
- Fix **spacing** on the landing page and dashboard: some items too narrow, some too wide.
- When a result is shown on a map and it names **routes**, draw those routes. A stop-only result draws no routes; a result with stops and routes draws both.
- Remove "These filters are added to the SQL WhyLine writes for your question." from the dashboard.
- Show on the dashboard **what topics can be asked about**.
- Allow **live questions** such as "What transit routes are running right now?": recognise them as live, write the SQL and show the results. A delay of **15–30 minutes** is acceptable, with a note in the UI where needed.

## PR A as built: polish, topics, site map

- **Topics** move to `frontend/src/lib/topics.ts`, shared by the landing page and a new collapsible "What can I ask about?" panel in Step 1 (`TopicsPanel`). Each topic's example clears any loaded question and fills the question box; nothing runs.
- **Site map** at `/site-map` (pages, home-page sections, documentation, `sitemap.xml`, `robots.txt`), linked from the footer and listed in `sitemap.xml`. The path isn't `/sitemap`, which would sit beside the generated `sitemap.xml` route.
- **Spacing:**
  - landing hero title wraps in three lines instead of four (`max-w-[14ch]`, up to 72 px);
  - the FAQ uses the full content width like the other sections;
  - the dashboard column is up to 1,000 px (was 920);
  - the whole-table download section lines up with the step cards and its card spans the column (it stopped at 720 px);
  - ranked bar charts size their label column from the chart's own width (about a third, 96–180 px), so the bars keep most of a phone-width card.
- The filter rail's explanatory line is gone; on phones the rail still shows when the data was updated.

## PR B as built: route lines on result maps

- **Models:** core `dim_route_shape` picks each route's most-run valid shape per direction in the latest GTFS extract (marts read only gold core; while a feed carries an upcoming runboard, its shape can win); `mart_route_shapes` simplifies it to about 10 m as GeoJSON. 258 shapes for 130 of 134 routes, 373 KB; the build scans about 17 MB because both reads inline the latest extract date. `allow_in_app: false`, so the dashboard can't query it and it isn't exported to DuckDB.
- **API:** `GET /api/routes/shapes?ids=` returns up to 10 routes' paths in request order. It reads the table once per process every 6 hours (one request at a time), splits the MultiLineStrings that simplifying produces (87 of 258) into separate paths, skips other geometry types and invalid or unknown IDs, and answers empty when the table can't be read, remembering the failure for 5 minutes.
- **Map:** a result with `route_id` gets the Map tab even without coordinates. `StopMap` draws the first 10 routes under the stop dots in ten distinct colors (none red, the stops' color), lists them with their names, says which routes have no line, and fits the view to the stops (a route-only result waits for its lines and fits them; lines arriving later never reset the user's view). A route-only result with no lines says so instead of showing an empty map. A stop-only result draws no lines. Tooltip text is HTML-escaped: result values are user-controlled, and the existing stop tooltip wasn't escaped either.
- **Release:** the tables appear after the next Nightly BigQuery build; the endpoint needs the next API image. Until both, maps show stops only.

## PR C: live questions

Views over the 15-minute realtime loads answer "right now" questions. Generated SQL that reads them is flagged as live, and the results say how old the newest record is. Ready-made "Which routes are running right now?" question. Expect 15–30 minutes of delay: the poller publishes every 15 minutes and `realtime-load` loads at :02, :17, :32 and :47.
