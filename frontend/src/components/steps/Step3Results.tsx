"use client";

import { useEffect, useState, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { runQuery, triggerDownload } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboardStore";
import { detectChartType, detectMapData } from "@/lib/chartLogic";
import { StepShell, type StepStatus } from "@/components/steps/StepShell";
import { DataTable } from "@/components/ui/DataTable";
import { RouteBarChart } from "@/components/viz/RouteBarChart";
import { TimeSeriesChart } from "@/components/viz/TimeSeriesChart";
import { WeatherSmallMultiples } from "@/components/viz/WeatherSmallMultiples";

const StopMap = dynamic(
  () => import("@/components/viz/StopMap").then((m) => m.StopMap),
  {
    ssr: false,
    loading: () => (
      <div className="h-[420px] rounded-[22px] bg-wl-canvas flex items-center justify-center font-bold text-wl-ink2">Loading map…</div>
    ),
  }
);

type View = "chart" | "map" | "table";
const VIEW_LABELS: Record<View, string> = { chart: "Chart", map: "Map", table: "Table" };

/** Step 3: run the query, then see the result as a chart, map or table and download it. */
export function Step3Results({ status }: { status: StepStatus }) {
  const { editedSql, sanitizedSql, generatedSql, question, sqlError, queryResult, runError, setQueryResult } =
    useDashboardStore();
  const [picked, setPicked] = useState<View | null>(null);
  // A new result opens on its best view (chart, then map, then table).
  useEffect(() => setPicked(null), [queryResult]);

  const mutation = useMutation({
    mutationFn: () => runQuery(sanitizedSql ?? editedSql, question),
    onSuccess: (data) => {
      setQueryResult(data.error ? null : data, data.error ?? null);
    },
    onError: (err) => {
      setQueryResult(null, String(err));
    },
  });

  const canRun = !!generatedSql && !sqlError;

  const chartType = useMemo(() => (queryResult ? detectChartType(queryResult.columns) : "none"), [queryResult]);
  const hasMap = useMemo(() => (queryResult ? detectMapData(queryResult.columns) : false), [queryResult]);

  const views: View[] = [
    ...(chartType !== "none" ? (["chart"] as const) : []),
    ...(hasMap ? (["map"] as const) : []),
    "table",
  ];
  const view = picked && views.includes(picked) ? picked : views[0];

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

  const result = queryResult && !queryResult.error ? queryResult : null;
  const isEmpty = result?.total_rows === 0;

  return (
    <StepShell n={3} title="See the results" status={status} last>
      {!canRun && !result ? (
        <p className="m-0 px-5 py-4 rounded-[22px] border-2 border-dashed border-wl-road text-[15px] font-bold text-wl-ink2">
          Run the checked SQL to see a table, plus a chart or map when the result has the right columns.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={!canRun || mutation.isPending}
            className={`wl-btn h-12 px-7 rounded-full font-black text-base text-white ${
              status === "current" ? "wl-btn-red bg-wl-red" : "wl-btn-navy bg-wl-navy"
            }`}
          >
            {mutation.isPending ? "Running…" : result ? "Run again" : "Run query"}
          </button>
          {result && (
            <span aria-live="polite" className="text-[15px] font-bold text-wl-ink2">
              {result.total_rows.toLocaleString()} {result.total_rows === 1 ? "row" : "rows"}
            </span>
          )}
        </div>
      )}

      {runError && (
        <p role="alert" className="mt-4 px-4 py-3 rounded-2xl bg-wl-red-tint text-[15px] font-bold text-wl-navy">
          The query didn’t run: {runError}
        </p>
      )}

      {result && isEmpty && (
        <p className="wl-enter mt-4 px-5 py-4 rounded-[22px] bg-wl-gold-tint text-[15px] font-bold text-wl-navy">
          No rows matched. Check the dates in the SQL against the data range in Filters, or try another question.
        </p>
      )}

      {result && !isEmpty && (
        <div className="wl-enter mt-4 bg-white rounded-[28px] p-2 wl-shadow">
          <div className="flex flex-wrap items-center gap-2 p-2">
            {views.length > 1 && (
              <div role="tablist" aria-label="Result view" className="inline-flex p-1 rounded-full bg-wl-canvas">
                {views.map((v) => (
                  <button
                    key={v}
                    type="button"
                    role="tab"
                    id={`wl-tab-${v}`}
                    aria-selected={view === v}
                    aria-controls="wl-result-panel"
                    onClick={() => setPicked(v)}
                    className={`h-10 px-5 rounded-full text-[15px] font-extrabold transition-colors ${
                      view === v ? "bg-wl-navy text-white" : "text-wl-navy hover:bg-white"
                    }`}
                  >
                    {VIEW_LABELS[v]}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={handleCsvDownload}
              className="wl-btn wl-btn-gold ml-auto inline-flex items-center gap-2 h-11 px-5 rounded-full bg-wl-gold text-wl-navy font-black text-[15px]"
            >
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />
              </svg>
              Download CSV
            </button>
          </div>

          <div id="wl-result-panel" role={views.length > 1 ? "tabpanel" : undefined} aria-labelledby={views.length > 1 ? `wl-tab-${view}` : undefined} className="p-2 sm:p-3">
            {view === "chart" && <ChartRenderer chartType={chartType} data={result.data} />}
            {view === "map" && (
              <>
                {result.total_rows > 1000 && (
                  <p className="mt-0 mb-2 text-[13px] font-bold text-wl-ink2">
                    Showing the first 1,000 of {result.total_rows.toLocaleString()} points.
                  </p>
                )}
                <StopMap data={result.data.slice(0, 1000)} />
              </>
            )}
            {view === "table" && <DataTable columns={result.columns} data={result.data} totalRows={result.total_rows} />}
          </div>
        </div>
      )}
    </StepShell>
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
          title="On-time share over time"
        />
      );
    }
    case "route_bar":
      return (
        <RouteBarChart
          data={data}
          xKey="route_id"
          yKey="avg_delay_ratio"
          title="Delay ratio by route, top 15"
        />
      );
    case "weather_multiples":
      return <WeatherSmallMultiples data={data} title="On-time share by weather" />;
    case "heatmap":
      // Simplified: render as grouped bar chart (full heatmap requires custom SVG)
      return (
        <RouteBarChart
          data={data.slice(0, 15)}
          xKey="stop_id"
          yKey="pct_on_time"
          title="On-time share by stop, first 15"
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
      return <RouteBarChart data={data} xKey={catCol} yKey={numCol} title={`${numCol} by ${catCol}`} />;
    }
    default:
      return null;
  }
}
