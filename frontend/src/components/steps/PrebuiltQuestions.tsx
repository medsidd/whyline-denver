"use client";

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
    onSuccess: (data, { index, label }) => {
      setQuestion(label);
      setSqlFromGeneration(data.sql, data.explanation, false, index);
    },
  });

  return (
    <div className="mt-5">
      <p className="m-0 text-sm font-extrabold text-wl-ink2">Or start from a ready-made question</p>
      <ul className="mt-2 mb-0 p-0 list-none grid sm:grid-cols-2 gap-x-6">
        {PREBUILT_QUERIES.map((q, i) => {
          const pending = mutation.isPending && mutation.variables?.index === q.index;
          const color = CHIP_COLORS[q.index] ?? TEAL;
          return (
            <li key={q.index}>
              <button
                type="button"
                onClick={() => mutation.mutate({ index: q.index, label: q.label })}
                disabled={mutation.isPending}
                className="w-full flex items-start gap-3 min-h-[44px] py-2.5 px-2 -mx-2 rounded-xl text-left text-[15px] font-extrabold text-wl-navy border-b-2 border-wl-navy/[0.06] hover:bg-white disabled:cursor-wait"
              >
                <span aria-hidden="true" className={`flex-none mt-[7px] w-2.5 h-2.5 rounded-full ${color.dot}`} />
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
