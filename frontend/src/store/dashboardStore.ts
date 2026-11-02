/**
 * Zustand store — replaces Streamlit's st.session_state.
 * Holds all client state for the dashboard.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { FilterState, RunQueryResponse } from "@/types/api";

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
    prebuiltIndex?: number | null
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

export function defaultFilters(): FilterState {
  const today = new Date();
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(today.getDate() - 7);
  return {
    start_date: sevenDaysAgo.toISOString().split("T")[0],
    end_date: today.toISOString().split("T")[0],
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
  queryResult: null,
  runError: null,

  // Actions
  setFilters: (partial) =>
    set((s) => ({ filters: { ...s.filters, ...partial } })),

  setQuestion: (question) => set({ question }),

  setSqlFromGeneration: (sql, explanation, cacheHit, prebuiltIndex = null) =>
    set({
      generatedSql: sql,
      prebuiltIndex,
      editedSql: sql,
      sanitizedSql: sql,
      explanation,
      sqlCacheHit: cacheHit,
      sqlError: null,
      bqEstBytes: null,
      // Clear previous results when new SQL is generated
      queryResult: null,
      runError: null,
    }),

  setEditedSql: (sql) =>
    set((s) => ({ editedSql: sql, prebuiltIndex: sql === s.generatedSql ? s.prebuiltIndex : null })),

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
