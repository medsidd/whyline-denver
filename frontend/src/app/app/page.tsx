"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { PrebuiltQuestions } from "@/components/steps/PrebuiltQuestions";
import { Step1QuestionInput } from "@/components/steps/Step1QuestionInput";
import { Step2SqlEditor } from "@/components/steps/Step2SqlEditor";
import { Step3Results } from "@/components/steps/Step3Results";
import { tokens } from "@/lib/tokens";

/**
 * /app — main dashboard page.
 * Sidebar (fixed left on desktop, slide-in drawer on mobile) + scrollable main column.
 */
export default function DashboardPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: "var(--color-background)" }}>
      {/* ── Mobile backdrop ──────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ─────────────────────────────────────────── */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* ── Main content ────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto flex flex-col min-w-0">
        <div className="max-w-4xl w-full mx-auto px-4 md:px-6 py-8 flex-1">
          {/* Hamburger — mobile only */}
          <button
            className="md:hidden mb-4 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{
              backgroundColor: tokens.surface,
              color: tokens.accent,
              border: `1px solid ${tokens.border}`,
              fontFamily: "var(--font-space-grotesk)",
            }}
            onClick={() => setSidebarOpen(true)}
          >
            ☰ Filters &amp; Settings
          </button>

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
