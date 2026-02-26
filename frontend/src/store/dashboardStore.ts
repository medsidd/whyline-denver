/**
 * Zustand store — replaces Streamlit's st.session_state.
 * Holds all client state for the dashboard.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Engine, FilterState, RunQueryResponse } from "@/types/api";

interface DashboardState {
  // ─── Sidebar ───────────────────────────────────────────────────────────
  engine: Engine;
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

  // ─── Step 3: Results ──────────────────────────────────────────────────
  queryResult: RunQueryResponse | null;
  runError: string | null;

  // ─── Actions ──────────────────────────────────────────────────────────

  setEngine: (engine: Engine) => void;
  setFilters: (filters: Partial<FilterState>) => void;
  setQuestion: (q: string) => void;

  /** Called after /api/sql/generate returns successfully */
  setSqlFromGeneration: (
    sql: string,
    explanation: string,
    cacheHit: boolean
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

  /** Reset Steps 2+3 when engine changes (mirrors Streamlit engine-switch behavior) */
  resetForEngineChange: () => void;

  /** Reset all query-related state when user starts a new question */
  resetForNewQuestion: () => void;
}

function defaultFilters(): FilterState {
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
  engine: "duckdb",
  filters: defaultFilters(),
  question: "",
  generatedSql: null,
  editedSql: "",
  sanitizedSql: null,
  explanation: "",
  sqlError: null,
  sqlCacheHit: false,
  bqEstBytes: null,
  queryResult: null,
  runError: null,

  // Actions
  setEngine: (engine) =>
    set((s) => {
      if (s.engine === engine) return {};
      // Mirror Streamlit: engine change clears Steps 2+3 but keeps question (Step 1)
      return {
        engine,
        generatedSql: null,
        editedSql: "",
        sanitizedSql: null,
        explanation: "",
        sqlError: null,
        sqlCacheHit: false,
        bqEstBytes: null,
        queryResult: null,
        runError: null,
      };
    }),

  setFilters: (partial) =>
    set((s) => ({ filters: { ...s.filters, ...partial } })),

  setQuestion: (question) => set({ question }),

  setSqlFromGeneration: (sql, explanation, cacheHit) =>
    set({
      generatedSql: sql,
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

  setEditedSql: (sql) => set({ editedSql: sql }),

  setValidation: (sanitizedSql, bqEstBytes, error) =>
    set({
      sanitizedSql,
      bqEstBytes,
      sqlError: error,
    }),

  setQueryResult: (queryResult, runError) => set({ queryResult, runError }),

  resetForEngineChange: () =>
    set({
      generatedSql: null,
      editedSql: "",
      sanitizedSql: null,
      explanation: "",
      sqlError: null,
      sqlCacheHit: false,
      bqEstBytes: null,
      queryResult: null,
      runError: null,
    }),

  resetForNewQuestion: () =>
    set({
      generatedSql: null,
      editedSql: "",
      sanitizedSql: null,
      explanation: "",
      sqlError: null,
      sqlCacheHit: false,
      bqEstBytes: null,
      queryResult: null,
      runError: null,
    }),
    }),
    {
      name: "whyline-dashboard",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        engine: s.engine,
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
