"use client";

import { useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { fetchPrebuilt } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { PREBUILT_QUERIES } from "@/types/api";

// The landing page's topic colors: reliability and service teal, safety red, weather gold, equity navy.
const TEAL = { dot: "bg-wl-teal" };
const CHIP_COLORS = [
  TEAL,
  { dot: "bg-wl-red" },
  { dot: "bg-wl-gold" },
  { dot: "bg-wl-navy" },
  TEAL, // frequency
  TEAL, // predictions
  TEAL, // missed trips
  TEAL, // slow segments
];

/**
 * Ready-made questions. Clicking one fetches validated SQL, narrowed by the
 * filter rail, and loads it into the editor directly, without calling the
 * language model. While it is loaded unedited, changing a filter reloads it.
 */
export function PrebuiltQuestions() {
  const { filters, prebuiltIndex, generatedSql, editedSql, setQuestion, setSqlFromGeneration } = useDashboardStore();

  // Only the newest request may load its SQL, so slow responses can't overwrite later ones.
  const latest = useRef(0);

  const mutation = useMutation({
    mutationFn: async ({ index }: { index: number; label: string; reload?: boolean; seq: number }) => {
      const data = await fetchPrebuilt(index, useDashboardStore.getState().filters);
      if (data.error) throw new Error(data.error);
      return data;
    },
    onSuccess: (data, { index, label, reload, seq }) => {
      if (seq !== latest.current) return;
      const s = useDashboardStore.getState();
      if (reload) {
        // The user moved on (another question, or edits) while this was loading
        if (s.prebuiltIndex !== index || s.editedSql !== s.generatedSql) return;
        // Same SQL (the changed filter doesn't apply here): keep the results
        if (data.sql === s.generatedSql) return;
      }
      setQuestion(label);
      const use = data.applied_filters && data.skipped_filters ? { applied: data.applied_filters, skipped: data.skipped_filters } : null;
      setSqlFromGeneration(data.sql, data.explanation, false, index, use);
    },
  });
  const load = (index: number, label: string, reload = false) => mutation.mutate({ index, label, reload, seq: ++latest.current });

  // Reloading is free: building the SQL makes no BigQuery call.
  const filtersKey = JSON.stringify(filters);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    if (prebuiltIndex === null || editedSql !== generatedSql) return;
    const q = PREBUILT_QUERIES.find((p) => p.index === prebuiltIndex);
    if (!q) return;
    const t = setTimeout(() => {
      const s = useDashboardStore.getState();
      if (s.prebuiltIndex === q.index && s.editedSql === s.generatedSql) load(q.index, q.label, true);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersKey]);

  return (
    <div className="mt-5">
      <p className="m-0 text-sm font-extrabold text-wl-ink2">Or start from a ready-made question</p>
      <ul className="mt-2 mb-0 p-0 list-none grid sm:grid-cols-2 gap-x-6">
        {PREBUILT_QUERIES.map((q, i) => {
          const pending = mutation.isPending && !mutation.variables?.reload && mutation.variables?.index === q.index;
          const color = CHIP_COLORS[q.index] ?? TEAL;
          return (
            <li key={q.index}>
              <button
                type="button"
                onClick={() => load(q.index, q.label)}
                disabled={mutation.isPending && !mutation.variables?.reload}
                className="w-full flex items-start gap-3 min-h-[44px] py-2.5 px-2 -mx-2 rounded-xl text-left text-[15px] font-extrabold text-wl-navy border-b-2 border-wl-navy/[0.06] hover:bg-white disabled:cursor-wait"
              >
                <span aria-hidden="true" className={`flex-none mt-[7px] w-2.5 h-2.5 rounded-full ${color.dot}`} />
                {pending ? "Loading…" : q.label}
              </button>
            </li>
          );
        })}
      </ul>
      {mutation.isError && !mutation.variables?.reload && (
        <p role="alert" className="mt-3 text-sm font-bold text-wl-red">
          That question didn’t load. Try again, or ask it in your own words.
        </p>
      )}
    </div>
  );
}
