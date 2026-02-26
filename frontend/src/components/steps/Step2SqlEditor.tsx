"use client";

import { useEffect, useRef, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { sql as sqlLang } from "@codemirror/lang-sql";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView } from "@codemirror/view";
import { validateSql } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { tokens } from "@/lib/tokens";

/** Human-readable bytes — mirrors display.py::human_readable_bytes */
function humanBytes(value: number | null): string {
  if (value === null) return "unknown";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  for (const unit of units) {
    if (size < 1024 || unit === "TB") return `${size.toFixed(2)} ${unit}`;
    size /= 1024;
  }
  return `${size.toFixed(2)} TB`;
}

const MAX_BYTES_BILLED = 2_000_000_000; // 2 GB default

// Custom dark theme matching brand colors
const brandTheme = EditorView.theme({
  "&": {
    backgroundColor: "#1a171d",
    color: "#e8d5c4",
    fontSize: "13px",
    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
    borderRadius: "10px",
    border: "3px solid #433f4c",
    minHeight: "240px",
  },
  ".cm-content": { padding: "12px 16px" },
  ".cm-line": { lineHeight: "1.6" },
  ".cm-focused": { outline: "none" },
  ".cm-editor.cm-focused": { borderColor: "#87a7b3", boxShadow: "0 0 0 3px rgba(135,167,179,0.2)" },
  ".cm-gutters": { backgroundColor: "#1a171d", borderRight: "1px solid #433f4c", color: "#9a8e7e" },
  ".cm-activeLineGutter": { backgroundColor: "#232129" },
  ".cm-activeLine": { backgroundColor: "rgba(135,167,179,0.06)" },
});

/**
 * Step 2: SQL Editor — mirrors sql_editor.py::render().
 * Uses CodeMirror 6 with SQL syntax highlighting.
 * Debounces validation calls (500ms) while the user types.
 */
export function Step2SqlEditor() {
  const {
    engine,
    generatedSql,
    editedSql,
    explanation,
    sqlCacheHit,
    sqlError,
    bqEstBytes,
    setEditedSql,
    setValidation,
  } = useDashboardStore();

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const validateMutation = useMutation({
    mutationFn: (s: string) => validateSql(s, engine),
    onSuccess: (data) => {
      setValidation(data.sanitized_sql, data.bq_est_bytes, data.error);
    },
    onError: (err) => {
      setValidation(null, null, String(err));
    },
  });

  const handleChange = useCallback(
    (value: string) => {
      setEditedSql(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        validateMutation.mutate(value);
      }, 500);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [engine]
  );

  // Re-validate when engine changes (different guardrails)
  useEffect(() => {
    if (editedSql) {
      validateMutation.mutate(editedSql);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine]);

  // Don't render if no SQL has been generated yet
  if (!generatedSql) {
    return (
      <section className="mb-8">
        <div
          className="px-4 py-3 rounded-xl text-sm border"
          style={{
            backgroundColor: `rgba(135, 167, 179, 0.08)`,
            borderColor: tokens.border,
            color: tokens.muted,
          }}
        >
          👆 Generate SQL from a question above to continue
        </div>
        <hr className="section-separator mt-6" />
      </section>
    );
  }

  return (
    <section className="mb-8">
      <h3
        className="text-xl font-bold mb-4"
        style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
      >
        Step 2: Review &amp; Edit SQL
      </h3>

      {sqlCacheHit && (
        <div
          className="px-4 py-2 rounded-xl text-sm mb-3 border"
          style={{
            backgroundColor: `rgba(135, 167, 179, 0.08)`,
            borderColor: tokens.primary,
            color: tokens.primary,
          }}
        >
          ⚡ Reused cached SQL for this question.
        </div>
      )}

      {explanation && (
        <details className="mb-4">
          <summary
            className="cursor-pointer text-sm font-medium px-4 py-2 rounded-lg"
            style={{
              backgroundColor: tokens.surface,
              color: tokens.accent,
              fontFamily: "var(--font-space-grotesk)",
            }}
          >
            Query Explanation
          </summary>
          <div
            className="mt-2 px-4 py-3 rounded-xl text-sm border"
            style={{
              backgroundColor: `rgba(135, 167, 179, 0.08)`,
              borderColor: tokens.border,
              color: tokens.text,
            }}
          >
            {explanation}
          </div>
        </details>
      )}

      {/* CodeMirror SQL editor */}
      <CodeMirror
        value={editedSql}
        extensions={[sqlLang(), brandTheme]}
        theme={oneDark}
        onChange={handleChange}
        basicSetup={{
          lineNumbers: true,
          foldGutter: false,
          highlightActiveLineGutter: true,
          highlightActiveLine: true,
          autocompletion: true,
        }}
      />

      {/* Validation status */}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {validateMutation.isPending ? (
          <span className="text-xs" style={{ color: tokens.muted }}>
            Validating…
          </span>
        ) : sqlError ? (
          <span className="text-sm font-medium" style={{ color: tokens.error }}>
            ❌ SQL Validation Error: {sqlError}
          </span>
        ) : (
          <span className="text-sm font-medium" style={{ color: tokens.success }}>
            ✓ SQL validated successfully
          </span>
        )}

        {/* BigQuery cost estimate */}
        {engine === "bigquery" && bqEstBytes !== null && (
          <span
            className="text-xs px-3 py-1 rounded-full border"
            style={{
              backgroundColor: `rgba(135, 167, 179, 0.1)`,
              borderColor: tokens.primary,
              color: tokens.primary,
            }}
          >
            📊 Estimated: {humanBytes(bqEstBytes)} (max {humanBytes(MAX_BYTES_BILLED)})
          </span>
        )}
      </div>

      <hr className="section-separator mt-6" />
    </section>
  );
}
