# Frontend

The WhyLine Denver dashboard is a Next.js 14 App Router application. This document covers the component structure, state management, visualization logic, and key patterns.

---

## Directory Structure

```
frontend/src/
├── app/
│   ├── layout.tsx             Root layout (fonts, metadata, providers)
│   ├── page.tsx               Landing page (server component)
│   ├── app/
│   │   └── page.tsx           Dashboard page (client component)
│   └── providers.tsx          Zustand + TanStack Query setup
│
├── components/
│   ├── layout/
│   │   ├── Header.tsx         Top navigation bar
│   │   ├── Sidebar.tsx        Engine toggle + filter controls
│   │   └── Footer.tsx         Attribution footer
│   │
│   ├── steps/
│   │   ├── Step1QuestionInput.tsx  Natural language input
│   │   ├── Step2SqlEditor.tsx      SQL editor + validation
│   │   ├── Step3Results.tsx        Results display
│   │   └── PrebuiltQuestions.tsx   4 prebuilt query cards
│   │
│   ├── viz/
│   │   ├── TimeSeriesChart.tsx     Recharts line chart
│   │   ├── RouteBarChart.tsx       Recharts horizontal bar chart
│   │   ├── WeatherSmallMultiples.tsx  2×2 Recharts grid
│   │   └── StopMap.tsx             Deck.gl + react-map-gl scatter map
│   │
│   └── ui/
│       ├── DataTable.tsx           Tabular results display
│       ├── DownloadPanel.tsx       CSV + warehouse export controls
│       └── FreshnessBadge.tsx      Data timestamp indicator
│
├── store/
│   └── dashboardStore.ts      Zustand store (full dashboard state)
│
├── types/
│   └── api.ts                 TypeScript types mirroring FastAPI models
│
└── lib/
    ├── api.ts                 API client functions (fetch wrappers)
    ├── chartLogic.ts          Chart auto-detection logic
    └── tokens.ts              Design tokens (colors, spacing)
```

---

## Dashboard Flow

The dashboard uses a 3-step sequential workflow. Each step is gated: Step 2 is hidden until Step 1 completes, Step 3 is hidden until Step 2 has valid SQL.

### Step 1: Ask Your Question (`Step1QuestionInput.tsx`)

The user types a natural language question in a textarea. Pressing "Generate SQL" (or `Cmd/Ctrl+Enter`) calls `POST /api/sql/generate`.

The `question`, `engine`, and `filters` from the Zustand store are sent as the request body. On success, `setSqlFromGeneration()` is called, which:
- Sets `generatedSql` and `editedSql` to the returned SQL
- Sets `explanation`
- Clears any previous query results

On start, `resetForNewQuestion()` clears Steps 2 and 3.

**Prebuilt questions**: `PrebuiltQuestions.tsx` renders 4 cards that call `POST /api/sql/prebuilt/{index}` directly, bypassing the LLM.

### Step 2: Review SQL (`Step2SqlEditor.tsx`)

A CodeMirror 6 editor displays the generated SQL with syntax highlighting. The user can freely edit the SQL.

Validation runs automatically with a 500ms debounce after each keystroke. `POST /api/sql/validate` is called with the current editor contents. Results update:
- `sanitizedSql` — the sanitized SQL string if valid
- `bqEstBytes` — BigQuery byte estimate (displayed as "~X MB" for BigQuery engine)
- `sqlError` — error message if validation failed

**Changing the engine**: Switching between DuckDB and BigQuery calls `setEngine()`, which clears Steps 2 and 3 but preserves the question.

### Step 3: Results (`Step3Results.tsx`)

"Run Query" calls `POST /api/query/run` using `sanitizedSql || editedSql`. On success:
- `DataTable` renders the results as a scrollable table
- Charts and map are auto-detected from column names (see below)
- `DownloadPanel` is always available for mart/warehouse downloads

---

## State Management

All state lives in a single Zustand store with localStorage persistence.

**File**: `frontend/src/store/dashboardStore.ts`

### State shape

```typescript
{
  // Sidebar
  engine: "duckdb" | "bigquery"       // default: "duckdb"
  filters: {
    start_date: string | null          // default: 7 days ago
    end_date: string | null            // default: today
    routes: string[]                   // default: []
    stop_id: string                    // default: ""
    weather: string[]                  // default: []
  }

  // Step 1
  question: string                     // default: ""

  // Step 2
  generatedSql: string | null          // null until Step 1 completes
  editedSql: string                    // tracks user edits in CodeMirror
  sanitizedSql: string | null          // from /api/sql/validate
  explanation: string                  // AI-generated query explanation
  sqlError: string | null              // validation error message
  sqlCacheHit: boolean                 // true if LLM returned cached result
  bqEstBytes: number | null            // BigQuery cost estimate

  // Step 3
  queryResult: RunQueryResponse | null // null until query runs
  runError: string | null              // execution error
}
```

### Persisted fields

The following are saved to localStorage under key `"whyline-dashboard"`:
`engine`, `filters`, `question`, `generatedSql`, `editedSql`, `explanation`, `sqlCacheHit`

Query results (`queryResult`, `runError`) are NOT persisted — they are session-only.

### Key actions

- `setEngine(engine)` — changes engine; resets Steps 2 and 3
- `setFilters(partial)` — merges partial filter updates
- `setSqlFromGeneration(sql, explanation, cacheHit)` — called after successful `/api/sql/generate`
- `setEditedSql(sql)` — real-time updates as user types in CodeMirror
- `setValidation(sanitizedSql, bqEstBytes, error)` — called after `/api/sql/validate`
- `setQueryResult(result, error)` — called after `/api/query/run`
- `resetForNewQuestion()` — clears Steps 2 and 3 at start of Step 1
- `resetForEngineChange()` — same as above, called when engine changes

---

## Visualization Logic

Charts and maps are auto-detected from the result column names. No user configuration is required.

### Chart type detection (`lib/chartLogic.ts`)

`detectChartType(columns: string[]): ChartType` checks columns in this priority order:

1. **Heatmap**: columns include `event_hour_mst` AND `pct_on_time` AND `stop_id`
2. **Weather small multiples**: columns include `precip_bin` AND `pct_on_time` AND `service_date_mst`
3. **Route bar chart**: columns include `route_id` AND `avg_delay_ratio`
4. **Time series**: columns include `service_date_mst` AND `pct_on_time`
5. **Generic bar chart**: data has at least one numeric column (`avg`, `count`, `sum`, `pct`, `score`, `ratio`) AND one categorical column (`id`, `name`, `route`, `stop`, `bin`, `type`, `category`)
6. **None**: no pattern matched

### Map detection

`detectMapData(columns: string[]): boolean` returns `true` if the result includes both `lat` and `lon` columns (case-insensitive).

`detectMapMetric(columns: string[]): string | null` selects the metric to color/size map points, checking in this order: `priority_score`, `priority_rank`, `crash_250m_cnt`, `crash_100m_cnt`, `vuln_score_0_100`, `reliability_score_0_100`, `pct_on_time`, then the first column matching `score`, `cnt`, `count`, `pct`, `ratio`, `avg`.

### Visualization components

| Component | Chart type | Library |
|-----------|-----------|---------|
| `TimeSeriesChart` | Line chart over `service_date_mst`; grouped by `route_id` or `stop_id` (top 5) | Recharts |
| `RouteBarChart` | Horizontal bars; top 15 routes by delay ratio | Recharts |
| `WeatherSmallMultiples` | 2×2 grid of line charts, one panel per `precip_bin` | Recharts |
| `StopMap` | Scatterplot; point color and size from detected metric | Deck.gl + react-map-gl |

**StopMap must be dynamically imported with `ssr: false`**:

```typescript
const StopMap = dynamic(() => import("@/components/viz/StopMap"), { ssr: false });
```

maplibre-gl (used internally by react-map-gl) requires browser APIs and will fail during Next.js server-side rendering.

---

## API Communication

**Next.js rewrite** (`next.config.mjs`):

```javascript
async rewrites() {
  if (!process.env.API_BASE_URL) return [];
  return [{ source: "/api/:path*", destination: `${process.env.API_BASE_URL}/api/:path*` }];
}
```

All `/api/*` fetch calls are proxied server-side to `API_BASE_URL`. The FastAPI URL is never exposed to the browser. `API_BASE_URL` is a server-side env var (not prefixed `NEXT_PUBLIC_`).

API client functions are in `lib/api.ts`:

```typescript
generateSql(question, engine, filters) → POST /api/sql/generate
validateSql(sql, engine) → POST /api/sql/validate
runQuery(sql, engine, question) → POST /api/query/run
fetchFilters(engine) → GET /api/filters/{engine}
fetchFreshness() → GET /api/freshness
downloadMart(request) → POST /api/downloads/mart
```

---

## TypeScript Types

`types/api.ts` mirrors the FastAPI Pydantic models:

```typescript
type Engine = "duckdb" | "bigquery"

interface FilterState {
  start_date: string | null
  end_date: string | null
  routes: string[]
  stop_id: string
  weather: string[]
}

interface GenerateSqlResponse {
  sql: string
  explanation: string
  cache_hit: boolean
  error: string | null
}

interface RunQueryResponse {
  rows: number
  columns: string[]
  data: Record<string, unknown>[]
  total_rows: number
  stats: Record<string, unknown>
  error: string | null
}
```

---

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `next` | 14.2.x | Framework, App Router, server rewrites |
| `react` | 18.3.x | UI |
| `zustand` | 4.5.x | State management + localStorage persistence |
| `@tanstack/react-query` | 5.x | Server state for filter options endpoint |
| `recharts` | 2.12.x | Charts (time series, bar, small multiples) |
| `deck.gl` | 9.0.x | Map scatter layer |
| `react-map-gl` | 8.0.x | Map base (CartoDB dark basemap via MapLibre) |
| `@uiw/react-codemirror` | 4.23.x | SQL editor with syntax highlighting |
| `tailwindcss` | 3.4.x | Styling |
| `date-fns` | 3.6.x | Date formatting and arithmetic |

---

## Development

```bash
cd frontend
npm install         # Install dependencies
npm run dev         # Start dev server at http://localhost:3000
npm run build       # Type-check + production build
npm run lint        # ESLint check
```

Ensure `frontend/.env.local` contains `API_BASE_URL=http://localhost:8000`.
