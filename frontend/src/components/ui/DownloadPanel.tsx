"use client";

import { useState } from "react";
import { track } from "@vercel/analytics";
import { DownloadError, TOO_MANY, downloadMartCsv, triggerDownload } from "@/lib/api";
import { denverDate, readableDate } from "@/lib/format";
import { useDashboardStore } from "@/store/dashboardStore";

const MART_OPTIONS = [
  { value: "mart_reliability_by_route_day", label: "Reliability by route and day" },
  { value: "mart_reliability_by_stop_hour", label: "Reliability by stop and hour" },
  { value: "mart_crash_proximity_by_stop", label: "Crashes near each stop" },
  { value: "mart_access_score_by_stop", label: "Access score by stop" },
  { value: "mart_vulnerability_by_stop", label: "Vulnerability by stop" },
  { value: "mart_priority_hotspots", label: "Priority hotspots" },
  { value: "mart_weather_impacts", label: "Weather impacts" },
  { value: "mart_service_frequency_by_stop", label: "Scheduled departures by stop and hour" },
  { value: "mart_frequent_network_by_route", label: "Route frequency and span" },
  { value: "mart_service_intensity_by_tract", label: "Scheduled service by census tract" },
  { value: "mart_prediction_accuracy_by_route_day", label: "Arrival-prediction accuracy by route and day" },
  { value: "mart_crowding_by_route_hour", label: "Crowding by route and hour" },
  { value: "mart_crowding_by_stop", label: "Crowding by stop and hour" },
  { value: "mart_service_delivered_by_route_day", label: "Missed trips by route and day" },
  { value: "mart_wait_by_stop_period", label: "Wait time by stop and time of day" },
  { value: "mart_wait_by_route_day", label: "Wait time by route and day" },
  { value: "mart_segment_speed_by_hour", label: "Speed between stops by hour" },
  { value: "mart_trip_runtime_by_route_day", label: "Trip run time by route and day" },
];

// Marts with a service date (DATED_MARTS in api/routers/downloads.py): filterable by date, newest rows first.
const DATED_MARTS = new Set([
  "mart_reliability_by_route_day",
  "mart_reliability_by_stop_hour",
  "mart_prediction_accuracy_by_route_day",
  "mart_crowding_by_route_hour",
  "mart_service_delivered_by_route_day",
  "mart_wait_by_route_day",
  "mart_trip_runtime_by_route_day",
]);

const label = "block text-sm font-extrabold text-wl-navy mb-1.5";
const outlineBtn =
  "wl-btn inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full border-2 border-wl-navy bg-white text-wl-navy font-black text-[15px] hover:bg-wl-navy-tint";

const DownloadIcon = () => (
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />
  </svg>
);

const MIN_ROWS = 1_000;
const MAX_ROWS = 2_000_000;

/** A plain sentence for a failed download, instead of the API's raw response. */
function downloadErrorMessage(err: unknown): string {
  const status = err instanceof DownloadError ? err.status : 0;
  if (status === 400 || status === 422) return "The server didn’t accept that request. Check the table and row limit.";
  if (status === 429) return TOO_MANY;
  if (status >= 500) return "The server couldn’t build that file. Try again, or pick a smaller row limit.";
  return "The download didn’t start. Check your connection and try again.";
}

/** Whole-table CSV download that doesn't need a question. */
export function DownloadPanel() {
  const [mart, setMart] = useState(MART_OPTIONS[0].value);
  const [limitRows, setLimitRows] = useState(200_000);
  const [useDates, setUseDates] = useState(true);
  const { start_date, end_date } = useDashboardStore((s) => s.filters);
  const dated = DATED_MARTS.has(mart);
  const haveDates = !!start_date && !!end_date;
  const datesOn = dated && useDates && haveDates;
  const limitOk = Number.isInteger(limitRows) && limitRows >= MIN_ROWS && limitRows <= MAX_ROWS;
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const handleMartDownload = async () => {
    if (!limitOk) return;
    setStatus("loading");
    setError(null);
    try {
      const blob = await downloadMartCsv({
        mart,
        limit_rows: limitRows,
        date_column: datesOn ? "service_date_mst" : null,
        date_start: datesOn ? start_date : null,
        date_end: datesOn ? end_date : null,
      });
      const range = datesOn ? `_${start_date}_to_${end_date}` : "";
      triggerDownload(blob, `${mart}${range}_${denverDate()}.csv`);
      track("download", { mart });
      setStatus("done");
    } catch (err) {
      setError(downloadErrorMessage(err));
      setStatus("error");
    }
  };

  return (
    <section aria-labelledby="wl-downloads" className="mt-14 pt-8 sm:pl-[68px] border-t-2 border-wl-navy/10">
      <h2 id="wl-downloads" className="m-0 font-black text-2xl tracking-[-0.01em]">
        Download a whole table
      </h2>
      <p className="mt-1.5 mb-0 text-[15px] font-semibold text-wl-ink2 max-w-[60ch]">
        No question needed. Pick a table and get it as CSV, up to the row limit you set.
      </p>

      <div className="mt-5 bg-white rounded-[28px] p-5 wl-shadow">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px]">
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
              min={MIN_ROWS}
              max={MAX_ROWS}
              step={1000}
              aria-invalid={!limitOk}
              aria-describedby={limitOk ? undefined : "wl-limit-hint"}
              onChange={(e) => setLimitRows(Number(e.target.value))}
              className="wl-field tabular-nums"
            />
            {!limitOk && (
              <span id="wl-limit-hint" className="block mt-1.5 text-[13px] font-bold text-[#A80F12]">
                Use a whole number from 1,000 to 2,000,000.
              </span>
            )}
          </label>
        </div>
        {dated ? (
          <label className="mt-3 flex items-start gap-2.5 text-[14px] font-bold text-wl-navy">
            <input
              type="checkbox"
              checked={datesOn}
              disabled={!haveDates}
              onChange={(e) => setUseDates(e.target.checked)}
              className="mt-1 w-4 h-4 accent-[#0D657F] disabled:opacity-50"
            />
            <span>
              Use the dates from Filters
              {haveDates ? ` (${readableDate(start_date)} to ${readableDate(end_date)})` : ""}
              <span className="block text-[13px] font-semibold text-wl-ink2">
                {haveDates ? "Newest rows first, up to the row limit." : "Set both dates in Filters to use them. Without dates, newest rows come first."}
              </span>
            </span>
          </label>
        ) : (
          <p className="mt-3 mb-0 text-[13px] font-semibold text-wl-ink2">This table has no dates, so the whole table downloads, up to the row limit.</p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" onClick={handleMartDownload} disabled={status === "loading" || !limitOk} className={`${outlineBtn} disabled:opacity-50 disabled:cursor-not-allowed`}>
            <DownloadIcon />
            {status === "loading" ? "Preparing…" : "Download CSV"}
          </button>
          <span role="status" className="text-[13px] font-bold">
            {status === "done" && <span className="text-wl-teal">Download started</span>}
            {error && <span className="text-[#A80F12]">{error}</span>}
          </span>
        </div>
      </div>
    </section>
  );
}
