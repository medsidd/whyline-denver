/**
 * Zustand store — replaces Streamlit's st.session_state.
 * Holds all client state for the dashboard.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { FilterName, FilterState, RunQueryResponse } from "@/types/api";
import { denverDate } from "@/lib/format";

/** How a ready-made question used the filter rail; null for other SQL or an older API. */
export type PrebuiltFilterUse = { applied: FilterName[]; skipped: FilterName[] } | null;

interface DashboardState {
  // ─── Sidebar ───────────────────────────────────────────────────────────
  filters: FilterState;

  // ─── Step 1: Question Input ────────────────────────────────────────────
  question: string;

  // ─── Step 2: SQL Editor ────────────────────────────────────────────────
  generatedSql: string | null;
  editedSql: string;
  sanitizedSql: string | null;
  explanation: string;
  sqlError: string | null;
  sqlCacheHit: boolean;
  bqEstBytes: number | null;
  /** Ready-made question whose SQL is loaded unedited; null otherwise. */
  prebuiltIndex: number | null;
  prebuiltFilters: PrebuiltFilterUse;
  /** Counts loads of new SQL, so the editor re-checks even when the text is unchanged. */
  generation: number;

  // ─── Step 3: Results ──────────────────────────────────────────────────
  queryResult: RunQueryResponse | null;
  runError: string | null;

  // ─── Actions ──────────────────────────────────────────────────────────

  setFilters: (filters: Partial<FilterState>) => void;
  setQuestion: (q: string) => void;

  /** Called after /api/sql/generate returns successfully */
  setSqlFromGeneration: (
    sql: string,
    explanation: string,
    cacheHit: boolean,
    prebuiltIndex?: number | null,
    prebuiltFilters?: PrebuiltFilterUse
  ) => void;

  /** Called as user types in the SQL editor */
  setEditedSql: (sql: string) => void;

  /** Called after /api/sql/validate returns */
  setValidation: (
    sanitizedSql: string | null,
    bqEstBytes: number | null,
    error: string | null
  ) => void;

  /** Called after /api/query/run returns */
  setQueryResult: (result: RunQueryResponse | null, error: string | null) => void;

  /** Reset all query-related state when user starts a new question */
  resetForNewQuestion: () => void;
}

/** The last seven days and today, by Denver's calendar (UTC was a day ahead every evening). */
export function defaultFilters(): FilterState {
  const today = denverDate();
  const start = new Date(`${today}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 7);
  return {
    start_date: start.toISOString().slice(0, 10),
    end_date: today,
    routes: [],
    stop_id: "",
    weather: [],
  };
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
  // Initial values
  filters: defaultFilters(),
  question: "",
  generatedSql: null,
  editedSql: "",
  sanitizedSql: null,
  explanation: "",
  sqlError: null,
  sqlCacheHit: false,
  bqEstBytes: null,
  prebuiltIndex: null,
  prebuiltFilters: null,
  generation: 0,
  queryResult: null,
  runError: null,

  // Actions
  setFilters: (partial) =>
    set((s) => ({ filters: { ...s.filters, ...partial } })),

  setQuestion: (question) => set({ question }),

  setSqlFromGeneration: (sql, explanation, cacheHit, prebuiltIndex = null, prebuiltFilters = null) =>
    set((s) => ({
      generation: s.generation + 1,
      generatedSql: sql,
      prebuiltIndex,
      prebuiltFilters,
      editedSql: sql,
      sanitizedSql: sql,
      explanation,
      sqlCacheHit: cacheHit,
      sqlError: null,
      bqEstBytes: null,
      // Clear previous results when new SQL is generated
      queryResult: null,
      runError: null,
    })),

  setEditedSql: (sql) =>
    // Clearing sanitizedSql makes Run use the visible text until its check returns (the API re-checks anyway).
    set((s) => ({
      editedSql: sql,
      sanitizedSql: sql === s.editedSql ? s.sanitizedSql : null,
      prebuiltIndex: sql === s.generatedSql ? s.prebuiltIndex : null,
    })),

  setValidation: (sanitizedSql, bqEstBytes, error) =>
    set({
      sanitizedSql,
      bqEstBytes,
      sqlError: error,
    }),

  setQueryResult: (queryResult, runError) => set({ queryResult, runError }),

  resetForNewQuestion: () =>
    set({
      generatedSql: null,
      editedSql: "",
      sanitizedSql: null,
      explanation: "",
      sqlError: null,
      sqlCacheHit: false,
      bqEstBytes: null,
      prebuiltIndex: null,
      prebuiltFilters: null,
      queryResult: null,
      runError: null,
    }),
    }),
    {
      name: "whyline-dashboard",
      // v1: BigQuery only. Drop older saved state, which can hold DuckDB-dialect SQL.
      version: 1,
      migrate: () => ({}) as DashboardState,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        filters: s.filters,
        question: s.question,
        generatedSql: s.generatedSql,
        editedSql: s.editedSql,
        explanation: s.explanation,
        sqlCacheHit: s.sqlCacheHit,
      }),
    }
  )
);
