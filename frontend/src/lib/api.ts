/**
 * Typed fetch wrappers for all WhyLine Denver API endpoints.
 * All paths are relative (/api/*) — Next.js rewrites proxy them to FastAPI.
 */

import type {
  Engine,
  FilterOptionsResponse,
  FilterState,
  FreshnessResponse,
  GenerateSqlResponse,
  MartDownloadRequest,
  ModelInfo,
  RunQueryResponse,
  ValidateSqlResponse,
} from "@/types/api";

const BASE = "";  // relative to current origin, rewrites handle the proxy

/** The dashboard queries BigQuery only; the API still accepts an engine per request. */
const ENGINE: Engine = "bigquery";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Filters ──────────────────────────────────────────────────────────────

export function fetchFilters(): Promise<FilterOptionsResponse> {
  return get(`/api/filters/${ENGINE}`);
}

export function fetchModels(): Promise<{ models: ModelInfo[] }> {
  return get("/api/models");
}

export function fetchFreshness(): Promise<FreshnessResponse> {
  return get("/api/freshness");
}

// ─── SQL ──────────────────────────────────────────────────────────────────

export function generateSql(
  question: string,
  filters: FilterState
): Promise<GenerateSqlResponse> {
  return post("/api/sql/generate", { question, engine: ENGINE, filters });
}

export function validateSql(sql: string): Promise<ValidateSqlResponse> {
  return post("/api/sql/validate", { sql, engine: ENGINE });
}

export function fetchPrebuilt(index: number): Promise<GenerateSqlResponse> {
  return post(`/api/sql/prebuilt/${index}/for/${ENGINE}`, {});
}

// ─── Query ────────────────────────────────────────────────────────────────

export function runQuery(sql: string, question: string): Promise<RunQueryResponse> {
  return post("/api/query/run", { sql, engine: ENGINE, question });
}

// ─── Downloads ────────────────────────────────────────────────────────────

export async function downloadMartCsv(req: Omit<MartDownloadRequest, "engine">): Promise<Blob> {
  const res = await fetch("/api/downloads/mart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, engine: ENGINE }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Mart download failed (${res.status}): ${text}`);
  }
  return res.blob();
}

/** Helper: trigger a browser file download from a Blob */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
