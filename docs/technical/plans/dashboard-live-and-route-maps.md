# Dashboard: live questions, route maps and polish

**Status:** active. PR A (polish, topics, site map) in review; PR B (route maps) and PR C (live questions) follow.

## Owner requests and decisions (November 9, 2026)

- Add a readable **site map** page and link it from the footer, alongside `sitemap.xml`.
- Fix **spacing** on the landing page and dashboard: some items too narrow, some too wide.
- When a result is shown on a map and it names **routes**, draw those routes. A stop-only result draws no routes; a result with stops and routes draws both.
- Remove "These filters are added to the SQL WhyLine writes for your question." from the dashboard.
- Show on the dashboard **what topics can be asked about**.
- Allow **live questions** such as "What transit routes are running right now?": recognise them as live, write the SQL and show the results. A delay of **15–30 minutes** is acceptable, with a note in the UI where needed.

## PR A as built: polish, topics, site map

- **Topics** move to `frontend/src/lib/topics.ts`, shared by the landing page and a new collapsible "What can I ask about?" panel in Step 1 (`TopicsPanel`). Each topic's example fills the question box; nothing runs.
- **Site map** at `/site-map` (pages, home-page sections, documentation, `sitemap.xml`, `robots.txt`), linked from the footer and listed in `sitemap.xml`. The path isn't `/sitemap`, which would sit beside the generated `sitemap.xml` route.
- **Spacing:**
  - landing hero title wraps in three lines instead of four (`max-w-[14ch]`, up to 72 px);
  - the FAQ uses the full content width like the other sections;
  - the dashboard column is up to 1,000 px (was 920);
  - the whole-table download section lines up with the step cards and its card spans the column (it stopped at 720 px);
  - ranked bar charts use a 112 px label column on phones (180 px on wider screens), so the bars keep most of the card.
- The filter rail's explanatory line is gone; on phones the rail still shows when the data was updated.

## PR B: route lines on result maps

A new mart table, `mart_route_shapes`, holds each current route's typical shape per direction as GeoJSON. It is built nightly and isn't queryable from the dashboard. A new endpoint returns the shapes for given route IDs, and `StopMap` draws them under the stop dots, one color per route, at most 10, with a legend. Results with route IDs and no coordinates also get a map.

## PR C: live questions

Views over the 15-minute realtime loads answer "right now" questions. Generated SQL that reads them is flagged as live, and the results say how old the newest record is. Ready-made "Which routes are running right now?" question. Expect 15–30 minutes of delay: the poller publishes every 15 minutes and `realtime-load` loads at :02, :17, :32 and :47.
