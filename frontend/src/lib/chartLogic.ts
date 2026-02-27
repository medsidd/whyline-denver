/**
 * Column-sniffing chart type selector — TypeScript port of charts.py::build_chart().
 * Detects which chart type best fits the query result columns.
 */

export type ChartType =
  | "heatmap"
  | "weather_multiples"
  | "route_bar"
  | "time_series"
  | "generic_bar"
  | "none";

export function detectChartType(columns: string[]): ChartType {
  const cols = new Set(columns.map((c) => c.toLowerCase()));

  // 1. Heatmap: stop×hour reliability
  if (cols.has("event_hour_mst") && cols.has("pct_on_time") && cols.has("stop_id")) {
    return "heatmap";
  }

  // 2. Weather small multiples
  if (cols.has("precip_bin") && cols.has("pct_on_time") && cols.has("service_date_mst")) {
    return "weather_multiples";
  }

  // 3. Route bar chart with delay ratio
  if (cols.has("route_id") && cols.has("avg_delay_ratio")) {
    return "route_bar";
  }

  // 4. Time series on-time %
  if (cols.has("service_date_mst") && cols.has("pct_on_time")) {
    return "time_series";
  }

  // 5. Generic: any numeric × any categorical
  const hasNumeric = columns.some((c) => ["avg", "count", "sum", "pct", "score", "ratio"].some(
    (kw) => c.toLowerCase().includes(kw)
  ));
  const hasCategorical = columns.some((c) =>
    ["id", "name", "route", "stop", "bin", "type", "category"].some((kw) =>
      c.toLowerCase().includes(kw)
    )
  );
  if (hasNumeric && hasCategorical) {
    return "generic_bar";
  }

  return "none";
}

/** Detect whether data has lat/lon for map rendering */
export function detectMapData(columns: string[]): boolean {
  const cols = new Set(columns.map((c) => c.toLowerCase()));
  return cols.has("lat") && cols.has("lon");
}

/** Find the best metric column for map radius/color scaling — mirrors build_map() priority */
export function detectMapMetric(columns: string[]): string | null {
  const priority = [
    "priority_score", "priority_rank",
    "crash_250m_cnt", "crash_100m_cnt",
    "vuln_score_0_100", "reliability_score_0_100",
    "pct_on_time",
  ];
  for (const col of priority) {
    if (columns.includes(col)) return col;
  }
  // Fallback to first numeric-looking column
  return columns.find((c) =>
    ["score", "cnt", "count", "pct", "ratio", "avg"].some((kw) => c.toLowerCase().includes(kw))
  ) ?? null;
}
