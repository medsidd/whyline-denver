"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchFilters, fetchFreshness } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { FreshnessBadge } from "@/components/ui/FreshnessBadge";
import { tokens } from "@/lib/tokens";
import type { Engine } from "@/types/api";

/**
 * Sidebar component — mirrors sidebar.py::render().
 * Contains: freshness badges, engine selector, date range, routes, stop ID, weather.
 */
export function Sidebar() {
  const { engine, filters, setEngine, setFilters } = useDashboardStore();

  // Filter options — refetched when engine changes
  const { data: filterData } = useQuery({
    queryKey: ["filters", engine],
    queryFn: () => fetchFilters(engine),
    staleTime: 5 * 60 * 1000,
  });

  // Freshness — refetched every 60s
  const { data: freshness } = useQuery({
    queryKey: ["freshness"],
    queryFn: fetchFreshness,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  // Derive freshness badge variants
  const bqFreshness = freshness?.bigquery_freshness ?? "Loading…";
  const duckFreshness = freshness?.duckdb_freshness ?? "Loading…";
  const bqVariant = bqFreshness.includes("Unavailable") ? "warning" : "success";
  const duckVariant = duckFreshness.includes("Unavailable") || duckFreshness.includes("Awaiting")
    ? "warning"
    : "accent";

  // Active filter summary items
  const activeFilters: string[] = [];
  if (filters.start_date && filters.end_date)
    activeFilters.push(`📅 ${filters.start_date} → ${filters.end_date}`);
  if (filters.routes.length)
    activeFilters.push(`🚌 Routes: ${filters.routes.slice(0, 3).join(", ")}${filters.routes.length > 3 ? "…" : ""}`);
  if (filters.stop_id)
    activeFilters.push(`🚏 Stop: ${filters.stop_id}`);
  if (filters.weather.length)
    activeFilters.push(`🌦️ Weather: ${filters.weather.join(", ")}`);

  return (
    <aside
      className="flex flex-col h-full overflow-y-auto p-5 gap-4"
      style={{
        width: "440px",
        minWidth: "280px",
        backgroundColor: tokens.surfaceDark,
        borderRight: `1px solid ${tokens.border}`,
      }}
    >
      {/* ── Freshness ───────────────────────────────────────── */}
      <section>
        <h2
          className="text-lg font-semibold mb-3"
          style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
        >
          Data Freshness
        </h2>
        <FreshnessBadge label="dbt (BigQuery)" value={bqFreshness} variant={bqVariant} />
        <FreshnessBadge label="DuckDB sync" value={duckFreshness} variant={duckVariant} />
        <p className="text-xs mt-1" style={{ color: tokens.muted }}>
          DuckDB holds ~90 days; BigQuery has the full corpus.
        </p>
      </section>

      <hr className="section-separator" />

      {/* ── Controls ────────────────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <h2
          className="text-lg font-semibold mb-1"
          style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
        >
          Controls
        </h2>

        {/* Engine selector */}
        <label className="block">
          <span className="block text-sm font-medium mb-1" style={{ color: tokens.muted }}>
            Query Engine
          </span>
          <div
            className="flex rounded-lg overflow-hidden border"
            style={{ borderColor: tokens.border, backgroundColor: tokens.surface }}
          >
            {(["duckdb", "bigquery"] as Engine[]).map((e) => (
              <button
                key={e}
                onClick={() => setEngine(e)}
                className="flex-1 py-2 px-3 text-sm font-semibold transition-colors"
                style={{
                  backgroundColor: engine === e ? tokens.primary : "transparent",
                  color: engine === e ? tokens.surfaceDark : tokens.text,
                  fontFamily: "var(--font-space-grotesk)",
                }}
              >
                {e === "duckdb" ? "DuckDB" : "BigQuery"}
              </button>
            ))}
          </div>
          <p className="text-xs mt-1" style={{ color: tokens.muted }}>
            {engine === "duckdb"
              ? "Fast local queries (~90 days)"
              : "Full cloud dataset — may be slower"}
          </p>
        </label>

        {/* Date range */}
        <label className="block">
          <span className="block text-sm font-medium mb-1" style={{ color: tokens.muted }}>
            Date Range
          </span>
          <div className="flex gap-2">
            <input
              type="date"
              value={filters.start_date ?? ""}
              min={filterData?.date_min ?? undefined}
              max={filterData?.date_max ?? undefined}
              onChange={(e) => setFilters({ start_date: e.target.value || null })}
              className="flex-1 rounded-lg px-3 py-2 text-sm border outline-none focus:ring-2"
              style={{
                backgroundColor: tokens.surface,
                borderColor: tokens.border,
                color: tokens.text,
              }}
            />
            <input
              type="date"
              value={filters.end_date ?? ""}
              min={filterData?.date_min ?? undefined}
              max={filterData?.date_max ?? undefined}
              onChange={(e) => setFilters({ end_date: e.target.value || null })}
              className="flex-1 rounded-lg px-3 py-2 text-sm border outline-none focus:ring-2"
              style={{
                backgroundColor: tokens.surface,
                borderColor: tokens.border,
                color: tokens.text,
              }}
            />
          </div>
          {filterData?.date_min && filterData?.date_max && (
            <p className="text-xs mt-1" style={{ color: tokens.muted }}>
              Available: {filterData.date_min} → {filterData.date_max}
            </p>
          )}
        </label>

        {/* Routes multi-select */}
        <label className="block">
          <span className="block text-sm font-medium mb-1" style={{ color: tokens.muted }}>
            Routes
          </span>
          <select
            multiple
            value={filters.routes}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions, (o) => o.value);
              setFilters({ routes: selected });
            }}
            className="w-full rounded-lg px-3 py-2 text-sm border outline-none"
            style={{
              backgroundColor: tokens.surface,
              borderColor: tokens.border,
              color: tokens.text,
              minHeight: "80px",
              maxHeight: "120px",
            }}
          >
            {(filterData?.routes ?? []).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <p className="text-xs mt-1" style={{ color: tokens.muted }}>
            Hold Ctrl/Cmd to select multiple. Leave blank for all routes.
          </p>
        </label>

        {/* Stop ID */}
        <label className="block">
          <span className="block text-sm font-medium mb-1" style={{ color: tokens.muted }}>
            Stop ID
          </span>
          <input
            type="text"
            value={filters.stop_id}
            placeholder="e.g. 12345"
            onChange={(e) => setFilters({ stop_id: e.target.value })}
            className="w-full rounded-lg px-3 py-2 text-sm border outline-none focus:ring-2"
            style={{
              backgroundColor: tokens.surface,
              borderColor: tokens.border,
              color: tokens.text,
            }}
          />
        </label>

        {/* Weather bins */}
        <label className="block">
          <span className="block text-sm font-medium mb-1" style={{ color: tokens.muted }}>
            Weather
          </span>
          <div className="flex flex-wrap gap-2">
            {(filterData?.weather_bins ?? ["none", "rain", "snow"]).map((bin) => (
              <button
                key={bin}
                onClick={() => {
                  const next = filters.weather.includes(bin)
                    ? filters.weather.filter((w) => w !== bin)
                    : [...filters.weather, bin];
                  setFilters({ weather: next });
                }}
                className="px-3 py-1 rounded-full text-xs font-semibold border transition-colors"
                style={{
                  backgroundColor: filters.weather.includes(bin)
                    ? tokens.primary
                    : tokens.surface,
                  borderColor: filters.weather.includes(bin) ? tokens.primary : tokens.border,
                  color: filters.weather.includes(bin) ? tokens.surfaceDark : tokens.text,
                }}
              >
                {bin}
              </button>
            ))}
          </div>
        </label>
      </section>

      {/* ── Active Filters Summary ───────────────────────────── */}
      {activeFilters.length > 0 && (
        <>
          <hr className="section-separator" />
          <section>
            <p className="text-xs font-semibold mb-2" style={{ color: tokens.muted }}>
              Active Filters
            </p>
            <ul className="flex flex-col gap-1">
              {activeFilters.map((f) => (
                <li key={f} className="text-xs" style={{ color: tokens.primary }}>
                  {f}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </aside>
  );
}
