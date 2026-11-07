/**
 * Column-sniffing chart type selector — TypeScript port of charts.py::build_chart().
 * Detects which chart type best fits the query result columns.
 */

export type ChartType =
  | "heatmap"
  | "weather_multiples"
  | "time_series"
  | "hour_bar"
  | "generic_bar"
  | "none";

/** `sql` and a sample `row` sharpen the bar-chart choice; see barColumns. */
export function detectChartType(columns: string[], sql?: string, row?: Record<string, unknown>): ChartType {
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

  // 4. A metric by hour of day, with nothing else to group by
  if (hourColumns(columns, sql, row)) return "hour_bar";

  // 5. Generic: any numeric × any categorical (route charts land here)
  return barColumns(columns, sql, row) ? "generic_bar" : "none";
}

const METRIC_KEYWORDS = ["avg", "count", "cnt", "sum", "pct", "share", "score", "ratio", "speed", "total", "delta", "n"];
const CATEGORY_KEYWORDS = ["id", "name", "route", "stop", "bin", "type", "category"];
const NOT_METRIC = new Set(["lat", "lon", "direction_id"]);
const HOUR = /(^|_)hour/;
/** Whether any of the column's underscore-separated words is a keyword. */
const has = (c: string, kws: string[]) => c.toLowerCase().split("_").some((w) => kws.includes(w));

/** First ORDER BY column, without a table alias. shortcut: a regex, not a SQL parser; good enough for one-level queries. */
export function orderByColumn(sql?: string): string | null {
  const m = sql && /\border\s+by\s+(?:\w+\.)?(\w+)/i.exec(sql);
  return m ? m[1].toLowerCase() : null;
}

function pickMetric(columns: string[], exclude: string, sql?: string, row?: Record<string, unknown>): string | undefined {
  const ok = (c: string) =>
    c !== exclude && !NOT_METRIC.has(c.toLowerCase()) && !HOUR.test(c.toLowerCase()) && (!row || typeof row[c] === "number");
  const ordered = orderByColumn(sql);
  const fromOrder = columns.find((c) => c.toLowerCase() === ordered && ok(c) && (!!row || has(c, METRIC_KEYWORDS)));
  return fromOrder ?? columns.find((c) => has(c, METRIC_KEYWORDS) && ok(c));
}

/**
 * Category and metric for a bar chart, or null when either is missing. The metric is the
 * column the SQL orders by when it's numeric, else the first metric-like column.
 */
export function barColumns(
  columns: string[],
  sql?: string,
  row?: Record<string, unknown>
): { category: string; metric: string } | null {
  const lower = columns.map((c) => c.toLowerCase());
  const pref = ["from_stop_name", "stop_name", "route_id", "route_name"].find((c) => lower.includes(c));
  const category = pref ? columns[lower.indexOf(pref)] : columns.find((c) => has(c, CATEGORY_KEYWORDS) && !HOUR.test(c.toLowerCase()));
  if (!category) return null;
  const metric = pickMetric(columns, category, sql, row);
  return metric ? { category, metric } : null;
}

/** Hour column and metric when a result is a metric by hour of day and nothing else is grouped. */
export function hourColumns(
  columns: string[],
  sql?: string,
  row?: Record<string, unknown>
): { hour: string; metric: string } | null {
  const hour = columns.find((c) => HOUR.test(c.toLowerCase()));
  if (!hour || columns.some((c) => c !== hour && has(c, CATEGORY_KEYWORDS))) return null;
  const metric = pickMetric(columns, hour, sql, row);
  return metric ? { hour, metric } : null;
}

/** Readable bar label: "from → to" for segments, else the category value with the route name when there is one. */
export function labelOf(columns: string[], category: string): (row: Record<string, unknown>) => string {
  const lower = new Set(columns.map((c) => c.toLowerCase()));
  if (category === "from_stop_name" && lower.has("to_stop_name")) {
    // The same segment can rank at several hours; lead with the hour so truncation keeps it.
    const hour = columns.find((c) => HOUR.test(c.toLowerCase()));
    return (r) => `${hour ? `${r[hour]}:00 ` : ""}${r.from_stop_name} → ${r.to_stop_name}`;
  }
  if (category === "route_id") {
    // The API adds route_name (often the same as the ID) and route_long_name to route results.
    return (r) => {
      const id = String(r.route_id ?? "");
      const name = [r.route_long_name, r.route_name].map((v) => (v ? String(v) : "")).find((v) => v && v !== id);
      return [id, name, lower.has("method") ? `(${r.method})` : ""].filter(Boolean).join(" ");
    };
  }
  return (r) => String(r[category] ?? "");
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
