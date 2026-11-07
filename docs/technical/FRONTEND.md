# Frontend

`frontend/` is a Next.js 14 App Router app with React 18. The landing page is `src/app/page.tsx`; the client dashboard is `src/app/app/page.tsx`. Dependency resolution is locked in `package-lock.json`.

## Component map

| Path under `frontend/src/` | Purpose |
|---|---|
| `app/layout.tsx`, `providers.tsx` | Fonts, metadata, TanStack Query provider, Vercel Analytics and Speed Insights |
| `components/layout/` | Header (glass nav, data freshness) and Sidebar (filter rail, collapsible below `lg`) |
| `components/steps/StepShell.tsx` | Numbered stop, connecting line and card for each step; status is done, current or upcoming |
| `components/steps/Step1QuestionInput.tsx` | Natural-language question and generation request; renders the ready-made questions |
| `components/steps/PrebuiltQuestions.tsx` | Eight ready-made question chips (BigQuery SQL from the API, narrowed by the filter rail; the list is `PREBUILT_QUERIES` in `types/api.ts`), colored by the landing page topic each belongs to. While one is loaded unedited, a filter change reloads it after 400 ms |
| `components/steps/Step2SqlEditor.tsx` | CodeMirror SQL editing (navy theme), validation on load and debounced while typing, BigQuery estimate, which filters a ready-made question used, and a note when edited SQL may not match the description |
| `components/steps/Step3Results.tsx` | Execution, Chart/Map/Table tabs, result CSV |
| `components/ui/` | DataTable, DownloadPanel (whole-table downloads below the steps) |
| `components/viz/` | TimeSeriesChart, RouteBarChart, WeatherSmallMultiples, StopMap |
| `store/dashboardStore.ts` | Multi-step state and selected localStorage persistence |
| `lib/api.ts`, `types/api.ts` | HTTP clients and TypeScript mirrors of API models |
| `lib/chartLogic.ts`, `tokens.ts` | Column-based visualization selection (the detector and the bar chart pick columns with the same `barColumns`/`hourColumns`; `labelOf` builds bar labels) and design tokens |
| `lib/format.ts` | Result display: share columns (`pct_*`, `*_pct_*`, `share_*`, `*_rate`, not `*pctl*`) as percentages in tables, axes and tooltips, coordinates to six decimals, readable column labels (`vuln_score_0_100` → "Vulnerability score (0–100)", `crash_250m_cnt` → "Number of crashes within 250 m"), 1000-based byte sizes, and the filter-use note. CSV downloads keep the raw values |

## State and workflow

The dashboard queries BigQuery only: `lib/api.ts` sends `engine: "bigquery"` on every request, and the UI has no engine switch or DuckDB download. The API still accepts `duckdb`. Generation sends question, engine, and filters to `/api/sql/generate`. On success, SQL/explanation populate the editor and prior results clear. Prebuilt cards bypass the LLM and call `/api/sql/prebuilt/{index}/for/bigquery` with the rail's filters; Step 2 then says which filters the question used ("Uses your dates and routes. Your stop filter isn't used by this question."). New SQL is validated as soon as it loads, so the scan estimate shows before any edit, and the pill reads "Checking…" until the check for the current text returns. Editing validates after a 500 ms debounce. Execution sends SQL to `/api/query/run`, which validates again server-side.

The Zustand store starts with a seven-day date range. Filter updates merge into state. They reload an unedited ready-made question but do not rewrite generated or edited SQL. Inspect the query after changing filters.

The route box reads "Loading routes…" until `/api/filters/bigquery` returns. A route entered before then is added once the list arrives; a route that isn't in the list gets an inline "No route called …" message. The whole-table download checks the row limit (1,000–2,000,000) before calling the API and shows API failures as plain sentences.

LocalStorage key `whyline-dashboard` (persist version 1; older saved state is discarded because it can hold DuckDB SQL) persists filters, question, generated SQL, edited SQL, explanation, and generation cache-hit state. Results, run errors, validation results, and byte estimates are not persisted. Closing a tab does not erase the persisted question/SQL. Persistence is per browser origin; no live cross-tab synchronization is implemented.

## Charts and maps

`detectChartType(columns, sql, row)` selects by column names, in order: stop/hour reliability, precipitation/date reliability, date reliability, a metric by hour with nothing else grouped (vertical bars sorted by hour), ranked categories (horizontal bars, up to 25, labels truncated with the full text on hover), or none. For bars, the metric is the column the run SQL's first `ORDER BY` names when it is numeric in the first row (a regex, not a parser), else the first metric-like column; `lat`, `lon` and `direction_id` never are. The category prefers `from_stop_name` (labelled "17:00 A → B"), `stop_name`, then `route_id` (with the route's long name when the API added one). This is a naming heuristic, not inferred statistical meaning.

The `heatmap` branch currently renders grouped bars rather than a full heatmap. Weather small multiples group precipitation categories; they do not prove snow-specific effects. Without an `ORDER BY` match, generic charts depend on name words such as `avg`, `pct` or `score`, not a full schema/type inspection.

`detectMapData()` checks for `lat` and `lon`. Metric preference starts with priority score/rank, crash counts, vulnerability, reliability score, and on-time share. See [metric definitions](../public/METRICS_GLOSSARY.md) before interpreting color or rank direction.

Always load the map dynamically:

```typescript
const StopMap = dynamic(() => import("@/components/viz/StopMap"), { ssr: false });
```

MapLibre requires browser APIs and must not execute during SSR.

## API proxy and downloads

`next.config.mjs` rewrites `/api/:path*` to `${API_BASE_URL}/api/:path*` when configured. Set `API_BASE_URL=http://localhost:8000` in `frontend/.env.local`, or the production Cloud Run origin in Vercel settings. It is server-side configuration; the proxy is not API authentication.

The results view can download displayed query data as CSV. DownloadPanel offers seven analytic mart CSVs from BigQuery. There is no public Parquet download control; Parquet is an internal synchronization format. See [API reference](API_REFERENCE.md).

## Development and validation

```bash
cd frontend
npm ci
npm run dev
npm run build
npm run lint
```

For repeated `EMFILE` watcher failures, use `WATCHPACK_POLLING=1000 npm run dev`. The build uses configured Google fonts and can need network access. Playwright is declared, but no specs/configuration are checked in; no Jest suite exists. See [testing](TESTING.md).

Privacy documentation must account for persisted browser state, provider requests, API logs, and the Analytics/Speed Insights components mounted in the root layout; do not claim that all state disappears when a tab closes.

## Design language

The landing page, legal pages and dashboard share the logo's colors as Tailwind `wl-*` tokens (`tailwind.config.ts`) and Nunito (`--font-nunito`, utility `font-rounded`). Pages wrap their content in `.wl`. Interaction and animation classes (`.wl-btn`, `.wl-field`, `.wl-rail`, the hero map, the scroll route, step pops) live in `globals.css` and respect `prefers-reduced-motion`. Motion is kept to the hero's load animation, the scroll route and responses to clicks: sections don't fade in on scroll and cards don't lift on hover. Landing sections are ruled lists (topics as a map legend, limits, sources, FAQ) rather than card grids. The dashboard's filter rail is a white card on phones, where it collapses, and an open column on desktop. `lib/tokens.ts` holds the same colors for code that can't use classes, plus the chart palette: five categorical hues in fixed order that pass the dataviz validator on white. Gold is below 3:1 contrast, so multi-series charts keep a legend and every result has a Table tab. The map uses CARTO's light Positron style.

On the dashboard the three steps are stops on one line. A step is done when its output exists (SQL written, SQL passes the check, result returned), and the first unfinished step is current and gets the red primary button.

`components/landing/ScrollRoute.tsx` is the header's route bar: a bus moves with page scroll and each stop is a section link. Stop positions are measured from the section ids, so keep `ROUTE_STOPS` in sync when sections change.

The hero question form and the suggestion chips open `/app?q=<question>`. `Step1QuestionInput` copies `q` into the question box, clears previous SQL and results, and removes `q` from the URL. It does not generate SQL; the user still clicks Write SQL. The landing page reads `/api/freshness` server-side (hourly revalidation) and hides the snapshot line when `API_BASE_URL` is unset or the API is unreachable.

Legal pages live at `/privacy`, `/terms` and `/attribution` (`components/landing/LegalPage.tsx` shell, linked from `SiteFooter`, which the dashboard also uses). The privacy policy describes current behavior: Gemini prompts, hashed query logs, the `whyline-dashboard` local-storage key, Vercel Analytics/Speed Insights, Google Cloud, and CARTO map tiles. Update it when any of those change. The Census Data API terms require `CENSUS_NOTICE` (`lib/links.ts`) to stay visible in the app.
