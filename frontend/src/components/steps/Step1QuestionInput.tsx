"use client";

import { useMutation } from "@tanstack/react-query";
import { generateSql } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { tokens } from "@/lib/tokens";

/**
 * Step 1: Natural language question input — mirrors question_input.py::render().
 */
export function Step1QuestionInput() {
  const {
    engine,
    filters,
    question,
    generatedSql,
    sqlCacheHit,
    sqlError,
    setQuestion,
    setSqlFromGeneration,
    resetForNewQuestion,
  } = useDashboardStore();

  const mutation = useMutation({
    mutationFn: () => generateSql(question, engine, filters),
    onMutate: () => {
      resetForNewQuestion();
    },
    onSuccess: (data) => {
      if (data.error) {
        useDashboardStore.setState({ sqlError: data.error });
        return;
      }
      setSqlFromGeneration(data.sql, data.explanation, data.cache_hit);
    },
    onError: (err) => {
      useDashboardStore.setState({ sqlError: String(err) });
    },
  });

  const handleGenerate = () => {
    if (!question.trim()) {
      useDashboardStore.setState({ sqlError: "Please enter a question before generating SQL." });
      return;
    }
    mutation.mutate();
  };

  return (
    <section className="mb-8">
      <h3
        className="text-xl font-bold mb-4"
        style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
      >
        Step 1: Ask Your Question
      </h3>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="e.g., Worst 10 routes in snow over the last 30 days"
        rows={3}
        className="w-full rounded-xl px-4 py-3 text-sm border outline-none resize-y"
        style={{
          backgroundColor: tokens.surface,
          borderColor: tokens.border,
          color: tokens.text,
          fontFamily: "var(--font-inter)",
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            handleGenerate();
          }
        }}
      />

      <div className="flex items-center gap-4 mt-3">
        <button
          onClick={handleGenerate}
          disabled={mutation.isPending}
          className="px-6 py-2.5 rounded-xl font-bold text-sm uppercase tracking-wide transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: `linear-gradient(135deg, ${tokens.accent} 0%, ${tokens.warning} 100%)`,
            color: tokens.surfaceDark,
            fontFamily: "var(--font-space-grotesk)",
            boxShadow: `0 4px 16px rgba(212, 165, 116, 0.3)`,
          }}
        >
          {mutation.isPending ? "Generating…" : "Generate SQL"}
        </button>

        {generatedSql && !sqlError && (
          <span className="text-sm font-medium" style={{ color: tokens.success }}>
            ✓ SQL generated successfully{sqlCacheHit ? " ⚡ (cached)" : ""}
          </span>
        )}
      </div>

      {sqlError && (
        <div
          className="mt-3 px-4 py-3 rounded-xl text-sm border"
          style={{
            backgroundColor: `rgba(199, 127, 109, 0.1)`,
            borderColor: tokens.error,
            color: tokens.error,
          }}
        >
          ❌ {sqlError}
        </div>
      )}

      <hr className="section-separator mt-6" />
    </section>
  );
}
