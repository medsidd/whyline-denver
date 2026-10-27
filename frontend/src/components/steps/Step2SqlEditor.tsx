"use client";

import { useEffect, useRef, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { sql as sqlLang } from "@codemirror/lang-sql";
import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";
import { validateSql } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { StepShell, type StepStatus } from "@/components/steps/StepShell";

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

// Navy editor, same colors as the SQL panel on the landing page
const navyTheme = EditorView.theme(
  {
    "&": {
      backgroundColor: "#021F38",
      color: "#E6EEF5",
      fontSize: "14px",
      borderRadius: "22px",
      minHeight: "200px",
    },
    ".cm-scroller": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", lineHeight: "1.75" },
    ".cm-content": { padding: "16px 8px", caretColor: "#F0B616" },
    ".cm-cursor": { borderLeftColor: "#F0B616", borderLeftWidth: "2px" },
    "&.cm-focused": { outline: "3px solid #7FD0E6", outlineOffset: "2px" },
    ".cm-gutters": { backgroundColor: "transparent", border: "none", color: "#5F7A93", paddingLeft: "10px" },
    ".cm-activeLineGutter": { backgroundColor: "transparent", color: "#B9CADB" },
    ".cm-activeLine": { backgroundColor: "rgba(255,255,255,0.04)" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "rgba(127,208,230,0.25)" },
    ".cm-tooltip": { backgroundColor: "#042F54", border: "none", borderRadius: "12px", overflow: "hidden" },
    ".cm-tooltip-autocomplete ul li[aria-selected]": { backgroundColor: "#0D657F", color: "#FFFFFF" },
  },
  { dark: true }
);

const navyHighlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: [t.keyword, t.operatorKeyword, t.function(t.variableName)], color: "#F0B616", fontWeight: "700" },
    { tag: [t.number, t.bool, t.null], color: "#FF9C8F" },
    { tag: [t.string, t.special(t.string)], color: "#7FD0E6" },
    { tag: [t.lineComment, t.blockComment], color: "#8FA6BC", fontStyle: "italic" },
    { tag: t.typeName, color: "#7FD0E6" },
  ])
);

const pill = "inline-flex items-center gap-1.5 h-8 px-3.5 rounded-full text-[13px] font-extrabold";

/**
 * Step 2: review and edit the SQL. Validation is debounced (500ms) while typing.
 */
export function Step2SqlEditor({ status }: { status: StepStatus }) {
  const {
    engine,
    generatedSql,
    editedSql,
    explanation,
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

  if (!generatedSql) {
    return (
      <StepShell n={2} title="Check the SQL" status={status}>
        <p className="m-0 px-5 py-4 rounded-[22px] border-2 border-dashed border-wl-road text-[15px] font-bold text-wl-ink2">
          The SQL for your question appears here. You can read it and edit it before anything runs.
        </p>
      </StepShell>
    );
  }

  const checkPill = validateMutation.isPending ? (
    <span className={`${pill} bg-wl-navy-tint text-wl-ink2`}>Checking…</span>
  ) : sqlError ? (
    <span className={`${pill} bg-wl-red-tint text-[#A80F12]`}>Can’t run yet</span>
  ) : (
    <span className={`${pill} bg-wl-teal-tint text-wl-teal`}>
      <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
      Read-only check passed
    </span>
  );

  return (
    <StepShell n={2} title="Check the SQL" status={status} aside={<span aria-live="polite">{checkPill}</span>}>
      <div className="wl-enter bg-white rounded-[28px] p-2 wl-shadow">
        {explanation && (
          <p className="m-0 px-4 pt-3 pb-4 text-[16px] font-semibold text-wl-ink2 max-w-[72ch]">
            <strong className="font-black text-wl-navy">What it does: </strong>
            {explanation}
          </p>
        )}
        <CodeMirror
          value={editedSql}
          aria-label="SQL query"
          extensions={[sqlLang(), navyHighlight, EditorView.lineWrapping]}
          theme={navyTheme}
          onChange={handleChange}
          basicSetup={{
            lineNumbers: true,
            foldGutter: false,
            highlightActiveLineGutter: true,
            highlightActiveLine: true,
            autocompletion: true,
          }}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 pt-3 pb-2 text-[13px] font-bold text-wl-ink2">
          <span>Edit freely. Only read-only queries on approved tables can run.</span>
          {engine === "bigquery" && bqEstBytes !== null && (
            <span className={`${pill} bg-wl-gold-tint text-wl-navy ml-auto`}>
              Scans about {humanBytes(bqEstBytes)} of {humanBytes(MAX_BYTES_BILLED)} allowed
            </span>
          )}
        </div>
      </div>

      {sqlError && !validateMutation.isPending && (
        <p role="alert" className="mt-3 px-4 py-3 rounded-2xl bg-wl-red-tint text-[15px] font-bold text-wl-navy">
          {sqlError}
        </p>
      )}
    </StepShell>
  );
}
