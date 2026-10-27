"use client";

import { useMutation } from "@tanstack/react-query";
import { fetchPrebuilt } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { PREBUILT_QUERIES } from "@/types/api";

// Same topic colors as the landing page chips, in PREBUILT_QUERIES order.
const CHIP_COLORS = [
  { tint: "bg-wl-teal-tint", dot: "bg-wl-teal" },
  { tint: "bg-wl-red-tint", dot: "bg-wl-red" },
  { tint: "bg-wl-gold-tint", dot: "bg-wl-gold" },
  { tint: "bg-wl-navy-tint", dot: "bg-wl-navy" },
];

/**
 * Ready-made questions. Clicking one fetches validated SQL and loads it into
 * the editor directly, without calling the language model.
 */
export function PrebuiltQuestions() {
  const { setQuestion, setSqlFromGeneration } = useDashboardStore();

  const mutation = useMutation({
    mutationFn: async ({ index }: { index: number; label: string }) => {
      const data = await fetchPrebuilt(index);
      if (data.error) throw new Error(data.error);
      return data;
    },
    onSuccess: (data, { label }) => {
      setQuestion(label);
      setSqlFromGeneration(data.sql, data.explanation, false);
    },
  });

  return (
    <div className="mt-5">
      <p className="m-0 text-sm font-extrabold text-wl-ink2">Or start from a ready-made question</p>
      <ul className="mt-2.5 flex flex-wrap gap-2">
        {PREBUILT_QUERIES.map((q, i) => {
          const pending = mutation.isPending && mutation.variables?.index === q.index;
          return (
            <li key={q.index}>
              <button
                type="button"
                onClick={() => mutation.mutate({ index: q.index, label: q.label })}
                disabled={mutation.isPending}
                className={`wl-chip inline-flex items-center gap-2 min-h-[40px] px-4 py-1.5 rounded-full text-left text-[15px] font-extrabold text-wl-navy disabled:cursor-wait ${CHIP_COLORS[i].tint}`}
              >
                <span aria-hidden="true" className={`flex-none w-2.5 h-2.5 rounded-full ${CHIP_COLORS[i].dot}`} />
                {pending ? "Loading…" : q.label}
              </button>
            </li>
          );
        })}
      </ul>
      {mutation.isError && (
        <p role="alert" className="mt-3 text-sm font-bold text-wl-red">
          That question didn’t load. Try again, or ask it in your own words.
        </p>
      )}
    </div>
  );
}
