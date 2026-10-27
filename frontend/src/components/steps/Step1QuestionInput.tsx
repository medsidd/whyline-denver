"use client";

import { useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { generateSql } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { PrebuiltQuestions } from "@/components/steps/PrebuiltQuestions";
import { StepShell, type StepStatus } from "@/components/steps/StepShell";

/** Step 1: ask in plain English, or load a ready-made question. */
export function Step1QuestionInput({ status }: { status: StepStatus }) {
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

  // Landing page links open /app?q=…: fill the box only, never auto-generate (no surprise LLM call).
  useEffect(() => {
    const url = new URL(window.location.href);
    const q = url.searchParams.get("q")?.trim();
    if (!q) return;
    resetForNewQuestion();
    setQuestion(q);
    url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
  }, [resetForNewQuestion, setQuestion]);

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
      useDashboardStore.setState({ sqlError: "Type a question first, or pick a ready-made one below." });
      return;
    }
    mutation.mutate();
  };

  return (
    <StepShell
      n={1}
      title="Ask a question"
      status={status}
      aside={
        generatedSql && !mutation.isPending && sqlCacheHit ? (
          <span className="inline-flex items-center h-7 px-3 rounded-full bg-wl-teal-tint text-[13px] font-extrabold text-wl-teal">
            Reused a saved answer
          </span>
        ) : null
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleGenerate();
        }}
        className="wl-ask bg-white rounded-[28px] p-2 wl-shadow"
      >
        <label htmlFor="wl-question" className="sr-only">
          Your question about Denver transit
        </label>
        <textarea
          id="wl-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Which routes were least on time in snow last month?"
          rows={2}
          className="block w-full min-h-[72px] px-4 pt-3 pb-1 border-0 bg-transparent resize-none text-lg font-bold text-wl-navy placeholder:text-[#6B7E90] placeholder:font-semibold focus:outline-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleGenerate();
            }
          }}
        />
        <div className="flex flex-wrap items-center justify-between gap-3 pl-4">
          <span className="hidden sm:inline text-[13px] font-bold text-wl-ink2">⌘ / Ctrl + Enter to write SQL</span>
          <button
            type="submit"
            disabled={mutation.isPending}
            className={`wl-btn ml-auto h-12 px-7 rounded-full font-black text-base text-white ${
              status === "current" ? "wl-btn-red bg-wl-red" : "wl-btn-navy bg-wl-navy"
            }`}
          >
            {mutation.isPending ? "Writing SQL…" : "Write SQL"}
          </button>
        </div>
      </form>

      {sqlError && !generatedSql && (
        <p role="alert" className="mt-3 px-4 py-3 rounded-2xl bg-wl-red-tint text-[15px] font-bold text-wl-navy">
          {sqlError}
        </p>
      )}

      <PrebuiltQuestions />
    </StepShell>
  );
}
