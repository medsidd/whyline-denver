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

export function fetchFilters(engine: Engine): Promise<FilterOptionsResponse> {
  return get(`/api/filters/${engine}`);
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
  engine: Engine,
  filters: FilterState
): Promise<GenerateSqlResponse> {
  return post("/api/sql/generate", { question, engine, filters });
}

export function validateSql(
  sql: string,
  engine: Engine
): Promise<ValidateSqlResponse> {
  return post("/api/sql/validate", { sql, engine });
}

export function fetchPrebuilt(
  index: number,
  engine: Engine
): Promise<GenerateSqlResponse> {
  return post(`/api/sql/prebuilt/${index}/for/${engine}`, {});
}

// ─── Query ────────────────────────────────────────────────────────────────

export function runQuery(
  sql: string,
  engine: Engine,
  question: string
): Promise<RunQueryResponse> {
  return post("/api/query/run", { sql, engine, question });
}

// ─── Downloads ────────────────────────────────────────────────────────────

export async function downloadMartCsv(req: MartDownloadRequest): Promise<Blob> {
  const res = await fetch("/api/downloads/mart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Mart download failed (${res.status}): ${text}`);
  }
  return res.blob();
}

export async function downloadWarehouse(): Promise<Blob> {
  const res = await fetch("/api/downloads/warehouse");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Warehouse download failed (${res.status}): ${text}`);
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
