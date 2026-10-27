"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { Step1QuestionInput } from "@/components/steps/Step1QuestionInput";
import { Step2SqlEditor } from "@/components/steps/Step2SqlEditor";
import { Step3Results } from "@/components/steps/Step3Results";
import type { StepStatus } from "@/components/steps/StepShell";
import { DownloadPanel } from "@/components/ui/DownloadPanel";
import { useDashboardStore } from "@/store/dashboardStore";

/**
 * /app — main dashboard page.
 * Filter rail (sticky left on desktop) + the three steps as stops on one route.
 */
export default function DashboardPage() {
  const { generatedSql, sqlError, queryResult } = useDashboardStore();

  // Each step is done once its output exists; the first unfinished one is current.
  const done = [!!generatedSql, !!generatedSql && !sqlError, !!queryResult];
  const firstOpen = done.indexOf(false);
  const status = (i: number): StepStatus => (done[i] ? "done" : i === firstOpen ? "current" : "upcoming");

  return (
    <div className="wl min-h-screen flex flex-col bg-wl-canvas text-wl-navy font-rounded font-medium">
      <Header />
      <div className="flex-1 w-full max-w-[1440px] mx-auto px-[clamp(16px,3vw,40px)] pt-6 lg:pt-8 pb-16 grid gap-6 lg:gap-10 lg:grid-cols-[300px_minmax(0,1fr)] items-start">
        <Sidebar />
        <main className="min-w-0 max-w-[920px]">
          <h1 className="m-0 font-black text-[clamp(30px,4vw,44px)] leading-[1.05] tracking-[-0.035em]">
            Ask about Denver transit
          </h1>
          <p className="mt-2 mb-8 text-[17px] text-wl-ink2 max-w-[60ch]">
            Ask in plain English or pick a ready-made question. Check the SQL WhyLine writes, then run it to see a table,
            chart or map.
          </p>
          <ol className="list-none m-0 p-0">
            <Step1QuestionInput status={status(0)} />
            <Step2SqlEditor status={status(1)} />
            <Step3Results status={status(2)} />
          </ol>
          <DownloadPanel />
        </main>
      </div>
      <SiteFooter />
    </div>
  );
}
