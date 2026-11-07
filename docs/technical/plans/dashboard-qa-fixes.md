# Dashboard QA fixes

**Status:** active. PR 1 in review; PRs 2 and 3 not started.

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
- **Downloads:** `DATE_COLUMNS` allows `service_date_mst` on the seven marts that have it; anything else returns 400.
- **Ready-made questions:** each has a label, an explanation, a template, a default date window and the filters it supports (table in [API reference](../API_REFERENCE.md#prebuilt-sql)). The endpoints take an optional `FilterState` body and return `applied_filters` and `skipped_filters`. Two labels lost their fixed window ("Worst 10 routes by on-time share", "Which routes missed the most scheduled trips?"). The prediction question's count column is `total_predictions`, not `n_predictions`: BigQuery resolved `HAVING SUM(n_predictions)` to the alias and rejected it as an aggregate of an aggregate. The crash and equity questions now also return `stop_name`, `lat` and `lon`, and equity returns `crash_score_0_100`.
- **Charts:** the bar metric is the first `ORDER BY` column when numeric. Ranked results are horizontal bars (25 rows, 28 px each, a 180 px label axis that truncates with a hover title). Segment labels read "17:00 A → B", because a segment can rank at several hours. A metric by hour gets vertical bars sorted by hour.
- **Compatibility:** the frontend deploys on merge but the API needs a new image. Until then the dashboard sends filters the old API ignores, shows no filter note (the fields are optional), and shows the old explanations.

## Verification

Before each merge: `make lint`, `pytest`, BigQuery dry runs of changed SQL, `npx tsc --noEmit`, `npm run lint`, `npm test`, `npm run build`, a local run of the dashboard against a local API, then green CI and the Vercel preview. After each merge and deploy: re-run the QA cases on production, add a dated [operations](../OPERATIONS.md) entry, and clear `whyline-dashboard` local storage in the QA browser.
