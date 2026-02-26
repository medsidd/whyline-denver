"use client";

import { useMutation } from "@tanstack/react-query";
import { fetchPrebuilt } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { tokens } from "@/lib/tokens";
import { PREBUILT_QUERIES } from "@/types/api";

/**
 * Prebuilt question buttons — mirrors prebuilt_questions.py::render().
 * 4 buttons in a 2×2 grid. Clicking one fetches validated SQL and populates
 * the SQL editor, skipping Step 1 (just like the Streamlit app).
 */
export function PrebuiltQuestions() {
  const { engine, setSqlFromGeneration } = useDashboardStore();

  const mutation = useMutation({
    mutationFn: ({ index }: { index: number }) => fetchPrebuilt(index, engine),
    onSuccess: (data) => {
      if (data.error) {
        console.error("Prebuilt query validation failed:", data.error);
        return;
      }
      setSqlFromGeneration(data.sql, data.explanation, false);
    },
  });

  return (
    <section className="mb-8">
      <h3
        className="text-xl font-bold mb-1"
        style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
      >
        Prebuilt Questions
      </h3>
      <p className="text-sm mb-4" style={{ color: tokens.muted }}>
        Click a button to load a ready-made query into the SQL editor
      </p>
      <div className="grid grid-cols-2 gap-3">
        {PREBUILT_QUERIES.map((q) => (
          <button
            key={q.index}
            onClick={() => mutation.mutate({ index: q.index })}
            disabled={mutation.isPending}
            className="px-4 py-3 rounded-xl text-sm font-semibold text-left border transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              backgroundColor: tokens.surface,
              borderColor: tokens.border,
              color: tokens.text,
              fontFamily: "var(--font-space-grotesk)",
              boxShadow: `0 2px 8px rgba(0,0,0,0.2)`,
            }}
          >
            {mutation.isPending ? "Loading…" : q.label}
          </button>
        ))}
      </div>
      {mutation.isError && (
        <p className="text-sm mt-2" style={{ color: tokens.error }}>
          ❌ Failed to load prebuilt query
        </p>
      )}
      <hr className="section-separator mt-6" />
    </section>
  );
}
