"use client";

import { useState } from "react";
import { downloadMartCsv, downloadWarehouse, triggerDownload } from "@/lib/api";
import { tokens } from "@/lib/tokens";
import type { Engine } from "@/types/api";

const MART_OPTIONS = [
  { value: "mart_reliability_by_route_day", label: "Reliability by route & day" },
  { value: "mart_reliability_by_stop_hour", label: "Reliability by stop & hour" },
  { value: "mart_crash_proximity_by_stop", label: "Crash proximity by stop" },
  { value: "mart_access_score_by_stop", label: "Access score by stop" },
  { value: "mart_vulnerability_by_stop", label: "Vulnerability by stop" },
  { value: "mart_priority_hotspots", label: "Priority hotspots" },
  { value: "mart_weather_impacts", label: "Weather impacts" },
];

interface Props {
  engine: Engine;
}

/** Downloads section — mirrors _render_downloads_section in results_viewer.py */
export function DownloadPanel({ engine }: Props) {
  const [open, setOpen] = useState(false);
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
    <div className="mt-8">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-xl border w-full"
        style={{
          backgroundColor: tokens.surface,
          borderColor: tokens.border,
          color: tokens.accent,
          fontFamily: "var(--font-space-grotesk)",
        }}
      >
        <span>{open ? "▾" : "▸"}</span> Downloads
      </button>

      {open && (
        <div
          className="mt-3 p-5 rounded-xl border"
          style={{ backgroundColor: tokens.surface, borderColor: tokens.border }}
        >
          {/* Full mart CSV exports */}
          <h4 className="text-sm font-bold mb-3" style={{ color: tokens.accent, fontFamily: "var(--font-space-grotesk)" }}>
            Full mart CSV exports
          </h4>

          <label className="block mb-3">
            <span className="text-xs font-medium block mb-1" style={{ color: tokens.muted }}>
              Choose mart
            </span>
            <select
              value={mart}
              onChange={(e) => setMart(e.target.value)}
              className="w-full rounded-lg px-3 py-2 text-sm border outline-none"
              style={{ backgroundColor: tokens.surfaceDark, borderColor: tokens.border, color: tokens.text }}
            >
              {MART_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className="block mb-4">
            <span className="text-xs font-medium block mb-1" style={{ color: tokens.muted }}>
              Row cap (safety)
            </span>
            <input
              type="number"
              value={limitRows}
              min={1000}
              max={2_000_000}
              step={1000}
              onChange={(e) => setLimitRows(Number(e.target.value))}
              className="w-full rounded-lg px-3 py-2 text-sm border outline-none"
              style={{ backgroundColor: tokens.surfaceDark, borderColor: tokens.border, color: tokens.text }}
            />
          </label>

          <button
            onClick={handleMartDownload}
            disabled={status === "loading"}
            className="w-full py-2 rounded-xl text-sm font-semibold border transition-colors disabled:opacity-50"
            style={{
              backgroundColor: tokens.surfaceDark,
              borderColor: tokens.success,
              color: tokens.success,
              fontFamily: "var(--font-space-grotesk)",
            }}
          >
            {status === "loading" ? "Preparing…" : "⬇️ Download Mart CSV"}
          </button>

          {status === "done" && (
            <p className="text-xs mt-2" style={{ color: tokens.success }}>✓ Download started</p>
          )}
          {error && (
            <p className="text-xs mt-2" style={{ color: tokens.error }}>❌ {error}</p>
          )}

          <hr className="section-separator my-4" />

          {/* DuckDB warehouse */}
          <h4 className="text-sm font-bold mb-3" style={{ color: tokens.accent, fontFamily: "var(--font-space-grotesk)" }}>
            DuckDB warehouse snapshot
          </h4>

          <button
            onClick={handleWarehouseDownload}
            disabled={warehouseStatus === "loading"}
            className="w-full py-2 rounded-xl text-sm font-semibold border transition-colors disabled:opacity-50"
            style={{
              backgroundColor: tokens.surfaceDark,
              borderColor: tokens.success,
              color: tokens.success,
              fontFamily: "var(--font-space-grotesk)",
            }}
          >
            {warehouseStatus === "loading" ? "Downloading…" : "🦆📦 Download DuckDB warehouse"}
          </button>
          {warehouseStatus === "error" && (
            <p className="text-xs mt-2" style={{ color: tokens.warning }}>
              ⚠️ Warehouse not available. Run make sync-duckdb first.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
