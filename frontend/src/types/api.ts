/**
 * TypeScript interfaces mirroring the Pydantic models in api/models.py.
 */

export type Engine = "duckdb" | "bigquery";

// ─── Filter / Sidebar ─────────────────────────────────────────────────────

export interface FilterState {
  start_date: string | null;
  end_date: string | null;
  routes: string[];
  stop_id: string;
  weather: string[];
}

// ─── Filter Options Response ───────────────────────────────────────────────

export interface FilterOptionsResponse {
  routes: string[];
  weather_bins: string[];
  date_min: string | null;
  date_max: string | null;
  error: string | null;
}

// ─── Models ───────────────────────────────────────────────────────────────

export interface ModelColumnInfo {
  name: string;
  type: string | null;
  description: string | null;
}

export interface ModelInfo {
  name: string;
  fq_name: string;
  description: string | null;
  columns: Record<string, ModelColumnInfo>;
}

export interface ModelsResponse {
  models: ModelInfo[];
}

// ─── SQL Generation ───────────────────────────────────────────────────────

export interface GenerateSqlRequest {
  question: string;
  engine: Engine;
  filters: FilterState;
}

export type FilterName = "dates" | "routes" | "stop" | "weather";

export interface GenerateSqlResponse {
  sql: string;
  explanation: string;
  cache_hit: boolean;
  error: string | null;
  /** Ready-made questions: filters applied to the SQL, and those set but not taken or invalid. Optional so an older API still parses. */
  applied_filters?: FilterName[];
  skipped_filters?: FilterName[];
  is_live?: boolean;
}

// ─── SQL Validation ───────────────────────────────────────────────────────

export interface ValidateSqlRequest {
  sql: string;
  engine: Engine;
}

export interface ValidateSqlResponse {
  valid: boolean;
  sanitized_sql: string | null;
  bq_est_bytes: number | null;
  error: string | null;
}

// ─── Query Execution ──────────────────────────────────────────────────────

export interface RunQueryRequest {
  sql: string;
  engine: Engine;
  question: string;
  prebuilt_index?: number | null;
}

export interface RunQueryResponse {
  rows: number;
  columns: string[];
  data: Record<string, unknown>[];
  total_rows: number;
  stats: Record<string, unknown>;
  error: string | null;
}

// ─── Downloads ────────────────────────────────────────────────────────────

export interface MartDownloadRequest {
  engine: Engine;
  mart: string;
  limit_rows: number;
  date_column: string | null;
  date_start: string | null;
  date_end: string | null;
}

// ─── Route shapes ─────────────────────────────────────────────────────────

export interface RouteShape {
  route_id: string;
  direction_id: number;
  /** [lon, lat] pairs */
  path: [number, number][];
}

// ─── Freshness ────────────────────────────────────────────────────────────

export interface FreshnessResponse {
  bigquery_freshness: string;
  duckdb_freshness: string;
}

// ─── Health ───────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  engine_default: string;
}

// ─── Prebuilt queries: labels mirror PREBUILT in src/whyline/prebuilt.py ──

export interface PrebuiltQuery {
  label: string;
  index: number;
}

export const PREBUILT_QUERIES: PrebuiltQuery[] = [
  { label: "Worst 10 routes by on-time share", index: 0 },
  { label: "Stops with highest crash exposure", index: 1 },
  { label: "Where snow hurts reliability most", index: 2 },
  { label: "Equity gaps (high vulnerability, low reliability)", index: 3 },
  { label: "How often do routes run, and which run every 15 minutes all day?", index: 4 },
  { label: "Which routes have the least reliable arrival predictions?", index: 5 },
  { label: "Which routes missed the most scheduled trips?", index: 6 },
  { label: "Where are the slowest bus segments at rush hour?", index: 7 },
  { label: "Which routes are running right now?", index: 8 },
];
