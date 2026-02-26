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

export interface GenerateSqlResponse {
  sql: string;
  explanation: string;
  cache_hit: boolean;
  error: string | null;
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

// ─── Prebuilt queries (front-end only) ────────────────────────────────────

export interface PrebuiltQuery {
  label: string;
  index: number;
}

export const PREBUILT_QUERIES: PrebuiltQuery[] = [
  { label: "Worst 10 routes (last 30 days)", index: 0 },
  { label: "Stops with highest crash exposure", index: 1 },
  { label: "Where snow hurts reliability most", index: 2 },
  { label: "Equity gaps (high vulnerability, low reliability)", index: 3 },
];
