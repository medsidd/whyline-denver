"use client";

import { useState, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { runQuery, triggerDownload } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { tokens } from "@/lib/tokens";
import { detectChartType, detectMapData } from "@/lib/chartLogic";
import dynamic from "next/dynamic";
import { DataTable } from "@/components/ui/DataTable";
import { DownloadPanel } from "@/components/ui/DownloadPanel";
import { RouteBarChart } from "@/components/viz/RouteBarChart";
import { TimeSeriesChart } from "@/components/viz/TimeSeriesChart";
import { WeatherSmallMultiples } from "@/components/viz/WeatherSmallMultiples";

const StopMap = dynamic(
  () => import("@/components/viz/StopMap").then((m) => m.StopMap),
  { ssr: false, loading: () => <div style={{ height: 400, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>Loading map…</div> }
);

/**
 * Step 3: Query execution and results display.
 * Mirrors results_viewer.py::render().
 */
export function Step3Results() {
  const {
    engine,
    editedSql,
    sanitizedSql,
    generatedSql,
    question,
    sqlError,
    queryResult,
    runError,
    setQueryResult,
  } = useDashboardStore();

  const [showStats, setShowStats] = useState(false);

  const mutation = useMutation({
    mutationFn: () => runQuery(sanitizedSql ?? editedSql, engine, question),
    onSuccess: (data) => {
      setQueryResult(data.error ? null : data, data.error ?? null);
    },
    onError: (err) => {
      setQueryResult(null, String(err));
    },
  });

  const canRun = !!generatedSql && !sqlError;

  const chartType = useMemo(
    () => (queryResult ? detectChartType(queryResult.columns) : "none"),
    [queryResult]
  );
  const hasMap = useMemo(
    () => (queryResult ? detectMapData(queryResult.columns) : false),
    [queryResult]
  );

  const handleCsvDownload = () => {
    if (!queryResult) return;
    const header = queryResult.columns.join(",");
    const rows = queryResult.data.map((row) =>
      queryResult.columns.map((c) => {
        const v = row[c];
        const s = v === null || v === undefined ? "" : String(v);
        return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(",")
    );
    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    triggerDownload(blob, "whylinedenver_results.csv");
  };

  // Show downloads-only view when no SQL has been generated
  if (!generatedSql && !queryResult) {
    return (
      <section className="mb-8">
        <h3 className="text-xl font-bold mb-2" style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}>
          Downloads
        </h3>
        <p className="text-sm mb-4" style={{ color: tokens.muted }}>
          Retrieve full marts or the DuckDB warehouse without generating SQL first.
        </p>
        <DownloadPanel engine={engine} />
      </section>
    );
  }

  return (
    <section className="mb-8">
      <h3 className="text-xl font-bold mb-4" style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}>
        Step 3: Results
      </h3>

      {/* Run button */}
      <div className="flex items-center gap-4 mb-4">
        <button
          onClick={() => mutation.mutate()}
          disabled={!canRun || mutation.isPending}
          className="px-6 py-2.5 rounded-xl font-bold text-sm uppercase tracking-wide transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: `linear-gradient(135deg, ${tokens.accent} 0%, ${tokens.warning} 100%)`,
            color: tokens.surfaceDark,
            fontFamily: "var(--font-space-grotesk)",
            boxShadow: `0 4px 16px rgba(212, 165, 116, 0.3)`,
          }}
        >
          {mutation.isPending ? "Running…" : "Run Query"}
        </button>

        {queryResult && !runError && (
          <span className="text-sm font-medium" style={{ color: tokens.success }}>
            ✓ Query executed successfully ({queryResult.total_rows.toLocaleString()} rows)
          </span>
        )}
      </div>

      {/* Errors */}
      {runError && (
        <div className="mb-4 px-4 py-3 rounded-xl text-sm border" style={{ backgroundColor: `rgba(199,127,109,0.1)`, borderColor: tokens.error, color: tokens.error }}>
          ❌ Query failed: {runError}
        </div>
      )}

      {/* Results */}
      {queryResult && !queryResult.error && (
        <>
          {/* Execution stats (collapsible) */}
          <details className="mb-4">
            <summary
              className="cursor-pointer text-sm font-medium px-4 py-2 rounded-lg"
              style={{ backgroundColor: tokens.surface, color: tokens.muted }}
              onClick={() => setShowStats(!showStats)}
            >
              Execution Statistics
            </summary>
            <pre
              className="mt-2 p-4 rounded-xl text-xs overflow-auto"
              style={{ backgroundColor: tokens.surfaceDark, color: tokens.text, border: `1px solid ${tokens.border}` }}
            >
              {JSON.stringify(queryResult.stats, null, 2)}
            </pre>
          </details>

          {/* Data table */}
          <DataTable
            columns={queryResult.columns}
            data={queryResult.data}
            totalRows={queryResult.total_rows}
          />

          {/* Chart visualization */}
          {chartType !== "none" && (
            <div className="mt-6">
              <ChartRenderer chartType={chartType} data={queryResult.data} />
            </div>
          )}

          {/* Map */}
          {hasMap && (
            <div className="mt-6">
              {queryResult.total_rows > 1000 && (
                <p className="text-xs mb-2" style={{ color: tokens.muted }}>
                  ℹ️ Map showing top 1,000 of {queryResult.total_rows.toLocaleString()} points
                </p>
              )}
              <StopMap data={queryResult.data.slice(0, 1000)} />
            </div>
          )}

          {/* CSV Download */}
          <div className="mt-4">
            <button
              onClick={handleCsvDownload}
              className="w-full py-2.5 rounded-xl text-sm font-semibold border transition-colors"
              style={{
                backgroundColor: tokens.surfaceDark,
                borderColor: tokens.success,
                color: tokens.success,
                fontFamily: "var(--font-space-grotesk)",
              }}
            >
              📥 Download Results as CSV
            </button>
          </div>
        </>
      )}

      {!queryResult && !runError && canRun && (
        <p className="text-sm" style={{ color: tokens.muted }}>👆 Run the query to see results</p>
      )}

      {/* Downloads panel always available */}
      <DownloadPanel engine={engine} />
    </section>
  );
}

/** Route chart type to component */
function ChartRenderer({
  chartType,
  data,
}: {
  chartType: string;
  data: Record<string, unknown>[];
}) {
  switch (chartType) {
    case "time_series": {
      const hasRoute = data[0] && "route_id" in data[0];
      const hasStop = data[0] && "stop_id" in data[0];
      return (
        <TimeSeriesChart
          data={data}
          xKey="service_date_mst"
          yKey="pct_on_time"
          groupKey={hasRoute ? "route_id" : hasStop ? "stop_id" : undefined}
          title="On-Time % Over Time"
        />
      );
    }
    case "route_bar":
      return (
        <RouteBarChart
          data={data}
          xKey="route_id"
          yKey="avg_delay_ratio"
          title="Route Delay Ratio (Top 15)"
        />
      );
    case "weather_multiples":
      return <WeatherSmallMultiples data={data} title="On-Time % by Weather Condition" />;
    case "heatmap":
      // Simplified: render as grouped bar chart (full heatmap requires custom SVG)
      return (
        <RouteBarChart
          data={data.slice(0, 15)}
          xKey="stop_id"
          yKey="pct_on_time"
          title="On-Time % by Stop"
        />
      );
    case "generic_bar": {
      const cols = Object.keys(data[0] ?? {});
      const catCol = cols.find((c) =>
        ["id", "name", "route", "stop", "bin", "type"].some((kw) => c.toLowerCase().includes(kw))
      ) ?? cols[0];
      const numCol = cols.find((c) =>
        ["avg", "count", "sum", "pct", "score", "ratio"].some((kw) => c.toLowerCase().includes(kw))
      ) ?? cols[1];
      if (!catCol || !numCol) return null;
      return <RouteBarChart data={data} xKey={catCol} yKey={numCol} />;
    }
    default:
      return null;
  }
}
