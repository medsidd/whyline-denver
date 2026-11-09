# Dashboard: live questions, route maps and polish

**Status:** active. PR A ([#132](https://github.com/medsidd/whyline-denver/pull/132)) and PR B ([#133](https://github.com/medsidd/whyline-denver/pull/133)) merged; PR C (live questions) in review. PRs B and C reach the app with the next Nightly BigQuery build and API image.

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

## PR C as built: live questions

- **Models:** core view `fct_vehicle_report` over the stream's vehicle reports (marts read only gold core), and two live mart views in `marts/live/`: `mart_vehicles_now` (vehicles running in the newest load: latest report in the last 45 minutes and within 10 minutes of the newest report, with route and stop names and `minutes_ago`) and `mart_stop_visits_recent` (stop visits in the last 2 hours including skipped stops, with delay and the nightly marts' on-time thresholds). Their time filters prune to today's partitions: about 2.6 MB and 1.3 MB a query. Run read-only against live data on November 9: 471 vehicles on 107 routes, reports 10–20 minutes old; 12,089 visits including 128 skipped.
- **Exposure:** `LIVE_MARTS` in `src/whyline/sync/constants.py`: queryable in the app on BigQuery (not DuckDB), never exported to Parquet or DuckDB.
- **Asking:** the prompt sends questions about right now, currently or live to the live views, tells the model not to date-filter them, and to say in the explanation that they trail real time by 15–30 minutes. The API marks SQL that reads them with `is_live` on generation, the check and the run; a live run also returns `live_loaded_at`, when the newest vehicle report was made. Found on the way: `EXTRACT(HOUR FROM ts)` was read as a table by the guardrail and by BigQuery qualification, which rejected hourly questions; fixed. They have no `service_date_mst`, so the date filter isn't injected.
- **Showing:** Steps 2 and 3 show a note when the API says the SQL reads a live view; Step 3's says when the newest vehicle report was made, and both give the 15–30 minute delay. Ready-made question 9, "Which routes are running right now?", counts vehicles per route; its map draws the route lines. A "Right now" topic joins the topics on the landing page and in the dashboard panel. The landing page's "A day behind" and the FAQ's live-arrivals answer are updated.
- **Release:** the views are created by the next Nightly BigQuery build; the API image carries the regenerated artifacts (committed in this PR; the catalog gains the views' column types once they exist). The API is backward compatible, so it is deployed before this PR merges: otherwise the frontend's question 9 would reach an API that doesn't have it.
