"use client";

import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchFreshness } from "@/lib/api";
import { DOCS, GLOSSARY } from "@/lib/links";
import { useDashboardStore } from "@/store/dashboardStore";

const _MT_FMT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZoneName: "short",
});

function toMountainTime(raw: string): string {
  if (
    !raw ||
    raw.startsWith("Loading") ||
    raw.startsWith("Unavailable") ||
    raw.startsWith("Awaiting") ||
    raw.startsWith("Latest run_date") ||
    raw.includes("MST") ||
    raw.includes("MDT")
  ) return raw;

  // Normalize "2026-03-08 20:05 UTC" → "2026-03-08T20:05Z"
  const normalized = raw.replace(" UTC", "Z").replace(/^(\d{4}-\d{2}-\d{2}) /, "$1T");
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return raw;

  const p = Object.fromEntries(_MT_FMT.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${p.timeZoneName}`;
}

/** Freshness for both engines, refetched every 60s; shared by the header and the filter rail. */
export function useFreshness() {
  const { data } = useQuery({
    queryKey: ["freshness"],
    queryFn: fetchFreshness,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  return {
    duckdb: toMountainTime(data?.duckdb_freshness ?? "Loading…"),
    bigquery: toMountainTime(data?.bigquery_freshness ?? "Loading…"),
  };
}

/** Sticky glass nav for the dashboard, matching the landing page. */
export function Header() {
  const engine = useDashboardStore((s) => s.engine);
  const value = useFreshness()[engine];
  const loading = value.startsWith("Loading");
  const stale = /Unavailable|Awaiting/.test(value);

  return (
    <header className="wl-nav sticky top-0 z-30 border-b border-wl-navy/[0.08]">
      <nav aria-label="Main" className="max-w-[1440px] mx-auto px-[clamp(16px,3vw,40px)] h-16 flex items-center gap-3 sm:gap-6">
        <Link href="/" className="flex items-center gap-2 sm:gap-2.5 min-h-[44px] text-wl-navy">
          <Image src="/assets/logo-512.png" alt="" width={36} height={36} priority />
          <span className="font-black text-[17px] sm:text-xl tracking-[-0.01em] whitespace-nowrap">WhyLine Denver</span>
        </Link>
        <span
          title={`${engine === "duckdb" ? "DuckDB" : "BigQuery"} data last updated`}
          className="hidden md:inline-flex items-center gap-2 h-9 px-3.5 rounded-full bg-white text-[13px] font-extrabold text-wl-ink2 wl-shadow"
        >
          <span aria-hidden="true" className={`w-2.5 h-2.5 rounded-full ${loading ? "bg-wl-road" : stale ? "bg-wl-gold" : "bg-wl-teal"}`} />
          {loading ? "Checking data…" : stale ? value : `Data updated ${value}`}
        </span>
        <div className="ml-auto flex items-center gap-1 sm:gap-2 text-[15px] font-extrabold">
          <a href={GLOSSARY} className="hidden sm:inline-flex items-center h-11 px-3 rounded-full hover:bg-white">
            Metric definitions
          </a>
          <a href={DOCS} className="inline-flex items-center h-11 px-3 rounded-full hover:bg-white">
            Docs
          </a>
        </div>
      </nav>
    </header>
  );
}
