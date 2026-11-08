# Dashboard QA fixes

**Status:** active. PR 1 merged ([#124](https://github.com/medsidd/whyline-denver/pull/124)), its API deployed by the owner on November 7, 2026 and verified on production. PR 2 in review; PR 3 not started.

## Why

On November 7, 2026 a full end-to-end QA of whylinedenver.com covered the landing page, all 8 ready-made questions, one Gemini-written question, rejected SQL, downloads, reload persistence, phone width, axe and link checks. The core flow worked. It found three groups of problems:

- **Correctness and trust.** Charts showed the wrong measure (the equity chart plotted vulnerability while the query ranked by priority), labels were IDs, "What it does" said only "Prebuilt query: …", typed routes were dropped silently, a typo got a misleading message, and the scan estimate appeared only after an edit.
- **Experience gaps.** No feedback during the 12-second wait for SQL; rough map, table and downloads.
- **Site hygiene.** No canonical links, robots.txt, sitemap or branded 404; one axe issue; no rate limits.

Code review found two SQL-injection paths: route and weather filter values were pasted into generated SQL unescaped, and the whole-table download pasted `date_column` into SQL unvalidated.

## Decisions (owner, November 7, 2026)

- Ready-made questions **apply the filter rail**.
- Rate limiting is a **Vercel firewall rule**.
- The work ships as **three PRs**, each merged and verified on production before the next starts.

## Scope

| PR | Contents |
|---|---|
| 1. Correctness, trust and security | Filter validation and the download date-column allowlist; ready-made questions as templates in `src/whyline/prebuilt.py` that take the filters, with real explanations; charts that plot the ranked measure with readable labels, an hour chart and horizontal ranked bars; scan estimate on load in 1000-based units; a note when edited SQL may not match its description; a plain guardrail message for a bad first word; route loading and no-match messages; a 10-minute filters cache; download row-limit checks and plain errors |
| 2. Dashboard experience | Waiting feedback; landing chips that load ready-made SQL (`/app?prebuilt=N`); map fit, size key and scroll lock; readable, sortable table; today left out of trend charts; CSV names with the question; whole-table downloads by the filter dates, newest first; schema-aware autocomplete; readable dates; "Precipitation" label; an LLM prompt that leaves dates to the server |
| 3. SEO, accessibility, 404 and rate limits | `metadataBase`, canonical and link-preview URLs; `robots.ts` and `sitemap.ts`; a branded 404; a focusable landing SQL block and skip links; a Vercel firewall rule (shown to the owner before production) with a friendly 429 message; the apex 307 → 308 redirect as a manual Vercel step |

**Out of scope:** a real SQL parser for guardrails or ORDER BY detection; Cloud Run ingress changes (so the firewall rule can be bypassed at the Cloud Run origin); a screen-reader audit; slow-network and cross-browser testing; Next.js's empty `role="alert"` route announcer.

## PR 1 as built

- **Filter validation** (`clean_filters`): routes and weather bins match `[A-Za-z0-9_-]{1,16}`, the stop `[A-Za-z0-9]{1,16}`, and dates must be ISO with the start on or before the end. Invalid values are dropped. Generated SQL and ready-made questions use the same predicate builders.
- **Downloads:** `DATED_MARTS` allows `service_date_mst` on the seven marts that have it; anything else returns 400.
- **Ready-made questions:** each has a label, an explanation, a template, a default date window and the filters it supports (table in [API reference](../API_REFERENCE.md#prebuilt-sql)). The endpoints take an optional `FilterState` body and return `applied_filters` and `skipped_filters`. Two labels lost their fixed window ("Worst 10 routes by on-time share", "Which routes missed the most scheduled trips?"). The prediction question's count column is `total_predictions`, not `n_predictions`: BigQuery resolved `HAVING SUM(n_predictions)` to the alias and rejected it as an aggregate of an aggregate. The crash and equity questions now also return `stop_name`, `lat` and `lon`, and equity returns `crash_score_0_100`.
- **Charts:** the bar metric is the first `ORDER BY` column when numeric. Ranked results are horizontal bars (25 rows, 28 px each, a 180 px label axis that truncates with a hover title). Segment labels read "17:00 A → B", because a segment can rank at several hours. A metric by hour gets vertical bars sorted by hour.
- **Compatibility:** the frontend deploys on merge but the API needs a new image. Until then the dashboard sends filters the old API ignores, shows no filter note (the fields are optional), and shows the old explanations.

## PR 2 as built

- **Waiting:** a live line under the question form ("Writing SQL… usually 10–20 seconds.", then seconds after 5); a skeleton in place of the result while a query runs.
- **Landing chips** link to `/app?prebuilt=N` and load that ready-made question without an AI call. The first chip is relabelled "Worst 10 routes by on-time share" to match.
- **Map:** mounts once measured and fits its points (40 px padding, zoom ≤ 14); a dot-size key under it; full screen locks page scroll and the button reads "Exit full screen". Full screen had never covered the page: the results card's entry animation kept an identity transform (`animation-fill-mode: both`), which traps `position: fixed`. It is now `backwards`.
- **Table:** readable headers ("Stop ID", "Vulnerability score (0–100)") with the raw name on hover; sorting with `aria-sort`; name columns moved next to their IDs.
- **Trends:** today's Denver date is left out of line charts and weather small multiples, with a note.
- **CSV names:** `whylinedenver_<question>_<date>.csv`; whole-table downloads add the date range.
- **Whole-table downloads:** "Use the dates from Filters", on by default, for the seven marts with a service date; the API returns them newest first.
- **Autocomplete:** approved tables and columns from `/api/models`, upper-case keywords, no emoji icons.
- **Dates:** "Nov 7, 5:05 PM MST" in the header and landing page, "Oct 23, 2025 to Nov 7, 2026" in the rail. The rail's default dates now follow Denver's calendar; they used the UTC date, a day ahead every evening.
- **Copy:** the rail's "Weather" is "Precipitation", and filter notes say "precipitation".
- **LLM prompt:** with dates set, the model is told the server adds the date range.
- **Dependency:** `@deck.gl/core` (already installed through `deck.gl`, same 9.2.9) is now declared, for `WebMercatorViewport`.

## Verification

Before each merge: `make lint`, `pytest`, BigQuery dry runs of changed SQL, `npx tsc --noEmit`, `npm run lint`, `npm test`, `npm run build`, a local run of the dashboard against a local API, then green CI and the Vercel preview. After each merge and deploy: re-run the QA cases on production, add a dated [operations](../OPERATIONS.md) entry, and clear `whyline-dashboard` local storage in the QA browser.
