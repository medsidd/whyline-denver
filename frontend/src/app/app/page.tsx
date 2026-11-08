"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { SkipLink } from "@/components/landing/SkipLink";
import { Step1QuestionInput } from "@/components/steps/Step1QuestionInput";
import { Step2SqlEditor } from "@/components/steps/Step2SqlEditor";
import { Step3Results } from "@/components/steps/Step3Results";
import type { StepStatus } from "@/components/steps/StepShell";
import { DownloadPanel } from "@/components/ui/DownloadPanel";
import { GLOSSARY, STOP_VISITS_SINCE } from "@/lib/links";
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
      <SkipLink />
      <Header />
      <div className="flex-1 w-full max-w-[1440px] mx-auto px-[clamp(16px,3vw,40px)] pt-6 lg:pt-8 pb-16 grid gap-6 lg:gap-10 lg:grid-cols-[300px_minmax(0,1fr)] items-start">
        <Sidebar />
        <main id="main" tabIndex={-1} className="min-w-0 max-w-[920px]">
          <h1 className="m-0 font-black text-[clamp(30px,4vw,44px)] leading-[1.05] tracking-[-0.035em]">
            Ask about Denver transit
          </h1>
          <p className="mt-2 mb-8 text-[17px] text-wl-ink2 max-w-[60ch]">
            Ask in plain English or pick a ready-made question. Check the SQL WhyLine writes, then run it to see a table,
            chart or map.
          </p>
          {STOP_VISITS_SINCE && (
            <details className="wl-faq -mt-4 mb-8 max-w-[64ch] rounded-2xl bg-wl-gold-tint px-4">
              <summary className="flex items-center justify-between gap-3 min-h-[48px] text-[15px] font-extrabold">
                On-time shares drop on {STOP_VISITS_SINCE}. Don’t compare across that date.
                <span aria-hidden="true" className="wl-plus flex-none w-7 h-7 rounded-full bg-white flex items-center justify-center text-lg leading-none">+</span>
              </summary>
              <p className="mt-0 pb-4 text-[15px] text-wl-ink2">
              Arrival times before {STOP_VISITS_SINCE} are estimated from 15-minute samples (accuracy ±minutes); from{" "}
              {STOP_VISITS_SINCE}, from 30-second vehicle reports (usually within 30 s for buses; each visit records its
              own uncertainty). On-time shares fall about 14 points at the switch, mostly because arrivals more than a
              minute early no longer count as on time, so don&apos;t compare the two periods. Bus figures also run 8–10
              points below RTD&apos;s own, mostly from how RTD counts at its timepoints.{" "}
              <a href={`${GLOSSARY}#changed-definitions-at-the-cutover`} className="text-wl-navy font-extrabold underline">
                How arrivals are timed
              </a>
              </p>
            </details>
          )}
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
