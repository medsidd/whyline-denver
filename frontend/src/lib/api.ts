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

export const TOO_MANY = "Too many requests. Wait a minute and try again.";

/** The rate limit (a Vercel firewall rule) answers 429; anything else keeps the API's status and text. */
async function failure(path: string, res: Response): Promise<Error> {
  if (res.status === 429) return new Error(TOO_MANY);
  return new Error(`API ${path} failed (${res.status}): ${await res.text()}`);
}

/** An error as a sentence, without the "Error: " prefix String() adds. */
export const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await failure(path, res);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw await failure(path, res);
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

/** A ready-made question's SQL, narrowed by the filters it supports. */
export function fetchPrebuilt(index: number, filters: FilterState): Promise<GenerateSqlResponse> {
  return post(`/api/sql/prebuilt/${index}/for/${ENGINE}`, filters);
}

// ─── Query ────────────────────────────────────────────────────────────────

/** `prebuiltIndex` marks a ready-made question run unedited, for usage counts. */
export function runQuery(sql: string, question: string, prebuiltIndex: number | null = null): Promise<RunQueryResponse> {
  return post("/api/query/run", { sql, engine: ENGINE, question, prebuilt_index: prebuiltIndex });
}

// ─── Downloads ────────────────────────────────────────────────────────────

export class DownloadError extends Error {
  constructor(public status: number) {
    super(`Download failed (${status})`);
  }
}

export async function downloadMartCsv(req: Omit<MartDownloadRequest, "engine">): Promise<Blob> {
  const res = await fetch("/api/downloads/mart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, engine: ENGINE }),
  });
  if (!res.ok) throw new DownloadError(res.status);
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
