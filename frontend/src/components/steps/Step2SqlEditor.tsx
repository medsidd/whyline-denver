"use client";

import { useEffect, useRef, useCallback, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { sql as sqlLang } from "@codemirror/lang-sql";
import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";
import { errorText, fetchModels, validateSql } from "@/lib/api";
import { filterUseNote, humanBytes, isLiveSql } from "@/lib/format";
import { LiveNote } from "@/components/steps/LiveNote";
import { useDashboardStore } from "@/store/dashboardStore";
import { StepShell, type StepStatus } from "@/components/steps/StepShell";

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
    ".cm-tooltip-autocomplete ul li": { padding: "2px 10px" },
    ".cm-completionIcon": { display: "none" },
    ".cm-completionDetail": { color: "#8FA6BC", fontStyle: "normal", marginLeft: "8px" },
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
    generatedSql,
    editedSql,
    explanation,
    sqlError,
    bqEstBytes,
    prebuiltFilters,
    generation,
    setEditedSql,
    setValidation,
  } = useDashboardStore();

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Autocomplete the approved tables and their columns, not just SQL keywords.
  const { data: modelData } = useQuery({ queryKey: ["models"], queryFn: fetchModels, staleTime: 60 * 60 * 1000 });
  const extensions = useMemo(() => {
    const schema = Object.fromEntries((modelData?.models ?? []).map((m) => [m.name, Object.keys(m.columns)]));
    return [
      sqlLang({ schema, upperCaseKeywords: true }),
      navyHighlight,
      EditorView.lineWrapping,
      // The wrapper's aria-label doesn't reach the editable element screen readers land on.
      EditorView.contentAttributes.of({ "aria-label": "SQL query" }),
    ];
  }, [modelData]);
  // The SQL the last finished check was for; anything else is still unchecked.
  const [checkedSql, setCheckedSql] = useState<string | null>(null);

  const validateMutation = useMutation({
    mutationFn: (s: string) => validateSql(s),
    // A check for text that has since changed is stale; drop it.
    onSuccess: (data, s) => {
      if (s !== useDashboardStore.getState().editedSql) return;
      setValidation(data.sanitized_sql, data.bq_est_bytes, data.error);
      setCheckedSql(s);
    },
    onError: (err, s) => {
      if (s !== useDashboardStore.getState().editedSql) return;
      setValidation(null, null, errorText(err));
      setCheckedSql(s);
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
    []
  );

  // Validate new SQL (generated, ready-made, or restored from the last visit), so the scan estimate shows
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (editedSql) {
      validateMutation.mutate(editedSql);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation]);

  if (!generatedSql) {
    return (
      <StepShell n={2} title="Check the SQL" status={status}>
        <p className="m-0 px-5 py-4 rounded-[22px] border-2 border-dashed border-wl-road text-[15px] font-bold text-wl-ink2">
          The SQL for your question appears here. You can read it and edit it before anything runs.
        </p>
      </StepShell>
    );
  }

  const checking = checkedSql !== editedSql;
  const edited = editedSql !== generatedSql;
  const checkPill = checking ? (
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
          <div className="px-4 pt-3 pb-4 max-w-[72ch]">
            <p className="m-0 text-[16px] font-semibold text-wl-ink2">
              <strong className="font-black text-wl-navy">What it does: </strong>
              {explanation}
            </p>
            {edited ? (
              <p className="mt-1.5 mb-0 text-[14px] font-bold text-wl-navy">
                You’ve edited the SQL, so this description may not match it.
              </p>
            ) : (
              prebuiltFilters &&
              filterUseNote(prebuiltFilters) && (
                <p className="mt-1.5 mb-0 text-[14px] font-bold text-wl-teal">{filterUseNote(prebuiltFilters)}</p>
              )
            )}
          </div>
        )}
        {isLiveSql(editedSql) && <LiveNote className="mx-2 mb-3" />}
        <CodeMirror
          value={editedSql}
          extensions={extensions}
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
          {bqEstBytes !== null && (
            <span className={`${pill} bg-wl-gold-tint text-wl-navy ml-auto`}>
              Scans about {humanBytes(bqEstBytes)} of {humanBytes(MAX_BYTES_BILLED)} allowed
            </span>
          )}
        </div>
      </div>

      {sqlError && !checking && (
        <p role="alert" className="mt-3 px-4 py-3 rounded-2xl bg-wl-red-tint text-[15px] font-bold text-wl-navy">
          {sqlError}
        </p>
      )}
    </StepShell>
  );
}
