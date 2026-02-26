"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { PrebuiltQuestions } from "@/components/steps/PrebuiltQuestions";
import { Step1QuestionInput } from "@/components/steps/Step1QuestionInput";
import { Step2SqlEditor } from "@/components/steps/Step2SqlEditor";
import { Step3Results } from "@/components/steps/Step3Results";

/**
 * /app — main dashboard page.
 * Sidebar (fixed left) + scrollable main column with all 3 steps.
 */
export default function DashboardPage() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: "var(--color-background)" }}>
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <Sidebar />

      {/* ── Main content ────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto flex flex-col min-w-0">
        <div className="max-w-4xl w-full mx-auto px-6 py-8 flex-1">
          <Header />

          {/* Prebuilt queries — quick-start shortcuts */}
          <PrebuiltQuestions />

          {/* Step 1: Natural language question */}
          <Step1QuestionInput />

          {/* Step 2: SQL editor + validation */}
          <Step2SqlEditor />

          {/* Step 3: Query execution + results + downloads */}
          <Step3Results />
        </div>

        <Footer />
      </main>
    </div>
  );
}
