"use client";

import { useState } from "react";
import { downloadMartCsv, downloadWarehouse, triggerDownload } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";

const MART_OPTIONS = [
  { value: "mart_reliability_by_route_day", label: "Reliability by route and day" },
  { value: "mart_reliability_by_stop_hour", label: "Reliability by stop and hour" },
  { value: "mart_crash_proximity_by_stop", label: "Crashes near each stop" },
  { value: "mart_access_score_by_stop", label: "Access score by stop" },
  { value: "mart_vulnerability_by_stop", label: "Vulnerability by stop" },
  { value: "mart_priority_hotspots", label: "Priority hotspots" },
  { value: "mart_weather_impacts", label: "Weather impacts" },
];

const label = "block text-sm font-extrabold text-wl-navy mb-1.5";
const outlineBtn =
  "wl-btn inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full border-2 border-wl-navy bg-white text-wl-navy font-black text-[15px] hover:bg-wl-navy-tint";

const DownloadIcon = () => (
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />
  </svg>
);

/** Whole-table downloads that don't need a question: a mart as CSV, or the DuckDB file. */
export function DownloadPanel() {
  const engine = useDashboardStore((s) => s.engine);
  const [mart, setMart] = useState(MART_OPTIONS[0].value);
  const [limitRows, setLimitRows] = useState(200_000);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [warehouseStatus, setWarehouseStatus] = useState<"idle" | "loading" | "error">("idle");

  const handleMartDownload = async () => {
    setStatus("loading");
    setError(null);
    try {
      const blob = await downloadMartCsv({
        engine,
        mart,
        limit_rows: limitRows,
        date_column: null,
        date_start: null,
        date_end: null,
      });
      triggerDownload(blob, `${mart}_${engine}_${new Date().toISOString().slice(0, 10)}.csv`);
      setStatus("done");
    } catch (err) {
      setError(String(err));
      setStatus("error");
    }
  };

  const handleWarehouseDownload = async () => {
    setWarehouseStatus("loading");
    try {
      const blob = await downloadWarehouse();
      triggerDownload(blob, "warehouse.duckdb");
      setWarehouseStatus("idle");
    } catch (err) {
      setWarehouseStatus("error");
      console.error(err);
    }
  };

  return (
    <section aria-labelledby="wl-downloads" className="mt-14 bg-wl-navy-tint rounded-[32px] p-[clamp(20px,3vw,36px)]">
      <h2 id="wl-downloads" className="m-0 font-black text-2xl tracking-[-0.01em]">
        Download whole tables
      </h2>
      <p className="mt-1.5 mb-0 text-[15px] font-semibold text-wl-ink2 max-w-[60ch]">
        No question needed. Take a full table as CSV, or the whole DuckDB file to query on your own computer.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="bg-white rounded-[24px] p-5">
          <h3 className="m-0 font-black text-lg">One table as CSV</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px]">
            <label>
              <span className={label}>Table</span>
              <select value={mart} onChange={(e) => setMart(e.target.value)} className="wl-field">
                {MART_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className={label}>Row limit</span>
              <input
                type="number"
                value={limitRows}
                min={1000}
                max={2_000_000}
                step={1000}
                onChange={(e) => setLimitRows(Number(e.target.value))}
                className="wl-field tabular-nums"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" onClick={handleMartDownload} disabled={status === "loading"} className={outlineBtn}>
              <DownloadIcon />
              {status === "loading" ? "Preparing…" : "Download CSV"}
            </button>
            <span role="status" className="text-[13px] font-bold">
              {status === "done" && <span className="text-wl-teal">Download started</span>}
              {error && <span className="text-[#A80F12]">The download failed: {error}</span>}
            </span>
          </div>
        </div>

        <div className="bg-white rounded-[24px] p-5 flex flex-col">
          <h3 className="m-0 font-black text-lg">DuckDB warehouse</h3>
          <p className="mt-1.5 mb-4 text-sm font-semibold text-wl-ink2">
            The recent ~90 days of every table in one file. Open it with DuckDB.
          </p>
          <div className="mt-auto flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleWarehouseDownload}
              disabled={warehouseStatus === "loading"}
              className={outlineBtn}
            >
              <DownloadIcon />
              {warehouseStatus === "loading" ? "Downloading…" : "Download .duckdb"}
            </button>
            {warehouseStatus === "error" && (
              <span role="status" className="text-[13px] font-bold text-[#A80F12]">
                The warehouse file isn’t available right now.
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
