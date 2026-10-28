# Frontend

`frontend/` is a Next.js 14 App Router app with React 18. The landing page is `src/app/page.tsx`; the client dashboard is `src/app/app/page.tsx`. Dependency resolution is locked in `package-lock.json`.

## Component map

| Path under `frontend/src/` | Purpose |
|---|---|
| `app/layout.tsx`, `providers.tsx` | Fonts, metadata, TanStack Query provider, Vercel Analytics and Speed Insights |
| `components/layout/` | Header (glass nav, data freshness) and Sidebar (filter rail, collapsible below `lg`) |
| `components/steps/StepShell.tsx` | Numbered stop, connecting line and card for each step; status is done, current or upcoming |
| `components/steps/Step1QuestionInput.tsx` | Natural-language question and generation request; renders the ready-made questions |
| `components/steps/PrebuiltQuestions.tsx` | Four ready-made question chips (BigQuery SQL from the API) |
| `components/steps/Step2SqlEditor.tsx` | CodeMirror SQL editing (navy theme), debounced validation, BigQuery estimate |
| `components/steps/Step3Results.tsx` | Execution, Chart/Map/Table tabs, result CSV |
| `components/ui/` | DataTable, DownloadPanel (whole-table downloads below the steps) |
| `components/viz/` | TimeSeriesChart, RouteBarChart, WeatherSmallMultiples, StopMap |
| `store/dashboardStore.ts` | Multi-step state and selected localStorage persistence |
| `lib/api.ts`, `types/api.ts` | HTTP clients and TypeScript mirrors of API models |
| `lib/chartLogic.ts`, `tokens.ts` | Column-based visualization selection and design tokens |

## State and workflow

The dashboard queries BigQuery only: `lib/api.ts` sends `engine: "bigquery"` on every request, and the UI has no engine switch or DuckDB download. The API still accepts `duckdb`. Generation sends question, engine, and filters to `/api/sql/generate`. On success, SQL/explanation populate the editor and prior results clear. Prebuilt cards bypass the LLM and call `/api/sql/prebuilt/{index}/for/bigquery`. Editing validates after a 500 ms debounce. Execution sends SQL to `/api/query/run`, which validates again server-side.

The Zustand store starts with a seven-day date range. Filter updates merge into state; they do not guarantee existing SQL is rewritten. Inspect the generated query after changing filters.

LocalStorage key `whyline-dashboard` (persist version 1; older saved state is discarded because it can hold DuckDB SQL) persists filters, question, generated SQL, edited SQL, explanation, and generation cache-hit state. Results, run errors, validation results, and byte estimates are not persisted. Closing a tab does not erase the persisted question/SQL. Persistence is per browser origin; no live cross-tab synchronization is implemented.

## Charts and maps

`detectChartType()` selects by column names, in order: stop/hour reliability, precipitation/date reliability, route delay ratio, date reliability, generic numeric/categorical names, or none. This is a naming heuristic, not inferred statistical meaning.

The `heatmap` branch currently renders grouped bars rather than a full heatmap. Weather small multiples group precipitation categories; they do not prove snow-specific effects. Generic charts depend on names such as `avg`, `pct`, or `score`, not a full schema/type inspection.

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

The landing page, legal pages and dashboard share the logo's colors as Tailwind `wl-*` tokens (`tailwind.config.ts`) and Nunito (`--font-nunito`, utility `font-rounded`). Pages wrap their content in `.wl`. Interaction and animation classes (`.wl-btn`, `.wl-card`, `.wl-field`, `.wl-reveal`, the hero map, the scroll route, step pops) live in `globals.css` and respect `prefers-reduced-motion`. `lib/tokens.ts` holds the same colors for code that can't use classes, plus the chart palette: five categorical hues in fixed order that pass the dataviz validator on white. Gold is below 3:1 contrast, so multi-series charts keep a legend and every result has a Table tab. The map uses CARTO's light Positron style.

On the dashboard the three steps are stops on one line. A step is done when its output exists (SQL written, SQL passes the check, result returned), and the first unfinished step is current and gets the red primary button.

`components/landing/ScrollRoute.tsx` is the header's route bar: a bus moves with page scroll and each stop is a section link. Stop positions are measured from the section ids, so keep `ROUTE_STOPS` in sync when sections change.

The hero question form and the suggestion chips open `/app?q=<question>`. `Step1QuestionInput` copies `q` into the question box, clears previous SQL and results, and removes `q` from the URL. It does not generate SQL; the user still clicks Write SQL. The landing page reads `/api/freshness` server-side (hourly revalidation) and hides the snapshot line when `API_BASE_URL` is unset or the API is unreachable.

Legal pages live at `/privacy`, `/terms` and `/attribution` (`components/landing/LegalPage.tsx` shell, linked from `SiteFooter`, which the dashboard also uses). The privacy policy describes current behavior: Gemini prompts, hashed query logs, the `whyline-dashboard` local-storage key, Vercel Analytics/Speed Insights, Google Cloud, and CARTO map tiles. Update it when any of those change. The Census Data API terms require `CENSUS_NOTICE` (`lib/links.ts`) to stay visible in the app.
