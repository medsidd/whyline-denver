/**
 * Column-sniffing chart type selector — TypeScript port of charts.py::build_chart().
 * Detects which chart type best fits the query result columns.
 */

export type ChartType =
  | "heatmap"
  | "weather_multiples"
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

  // 3. Time series on-time %
  if (cols.has("service_date_mst") && cols.has("pct_on_time")) {
    return "time_series";
  }

  // 4. Generic: any numeric × any categorical (route charts land here)
  return barColumns(columns) ? "generic_bar" : "none";
}

const METRIC_KEYWORDS = ["avg", "count", "cnt", "sum", "pct", "share", "score", "ratio"];
const CATEGORY_KEYWORDS = ["id", "name", "route", "stop", "bin", "type", "category"];
const has = (c: string, kws: string[]) => kws.some((kw) => c.toLowerCase().includes(kw));

/** The first category-like and metric-like columns, or null when either is missing. */
export function barColumns(columns: string[]): { category: string; metric: string } | null {
  const category = columns.find((c) => has(c, CATEGORY_KEYWORDS));
  const metric = columns.find((c) => has(c, METRIC_KEYWORDS) && c !== category);
  return category && metric ? { category, metric } : null;
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
