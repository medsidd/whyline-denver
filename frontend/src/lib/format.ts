/** Display formatting for query results: shares as percentages, readable column labels. */

/** A 0–1 share or a difference of shares (pct_on_time, share_missed_likely); "pctl" is a 0–100 percentile. */
export function isShareColumn(col: string): boolean {
  const c = col.toLowerCase();
  return !c.includes("pctl") && (/(^|_)(pct|share)(_|$)/.test(c) || c.endsWith("_rate"));
}

/** Percent for share columns (unless the SQL already scaled them past 1), fixed decimals for coordinates. */
export function formatValue(col: string, val: unknown): string {
  if (val === null || val === undefined) return "";
  if (typeof val !== "number") return String(val);
  if (isShareColumn(col) && Math.abs(val) <= 1) return `${(val * 100).toFixed(1)}%`;
  if (Number.isInteger(val)) return String(val);
  if (["lat", "lon"].includes(col.toLowerCase())) return val.toFixed(6);
  return val.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Axis ticks: whole percents for shares, otherwise the number as is. */
export const axisTick = (col: string) => (v: number) =>
  isShareColumn(col) && Math.abs(v) <= 1 ? `${Math.round(v * 100)}%` : String(v);

const WORDS: Record<string, string> = {
  avg: "average",
  cnt: "count",
  delta: "change in",
  id: "",
  kmh: "(km/h)",
  min: "(min)",
  mst: "",
  n: "number of",
  p50: "median",
  p90: "90th percentile",
  pct: "%",
  sec: "(s)",
  vuln: "vulnerability",
  "250m": "within 250 m",
  "100m": "within 100 m",
};

/** "avg_pct_on_time" -> "Average % on time", "route_id" -> "Route", "vuln_score_0_100" -> "Vulnerability score (0–100)". */
export function columnLabel(col: string): string {
  let lower = col.toLowerCase();
  const scale = lower.endsWith("_0_100");
  if (scale) lower = lower.slice(0, -"_0_100".length);
  // "crash_250m_cnt" -> "Number of crashes within 250 m"
  if (lower.endsWith("_cnt")) lower = `n_${lower.slice(0, -"_cnt".length).replace(/(^|_)crash(_|$)/, "$1crashes$2")}`;
  const s =
    lower
      .split("_")
      .map((w) => WORDS[w] ?? w)
      .filter(Boolean)
      .join(" ") + (scale ? " (0–100)" : "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Human-readable bytes in 1000-based units, as BigQuery bills them: 2,000,000,000 is "2 GB". */
export function humanBytes(value: number | null): string {
  if (value === null) return "unknown";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  for (const unit of units) {
    if (size < 1000 || unit === "TB") return `${Number(size.toFixed(2))} ${unit}`;
    size /= 1000;
  }
  return `${Number(size.toFixed(2))} TB`;
}

const FILTER_WORDS = { dates: "dates", routes: "routes", stop: "stop", weather: "weather" } as const;
const joinWords = (w: string[]) => (w.length < 2 ? w.join("") : `${w.slice(0, -1).join(", ")} and ${w[w.length - 1]}`);

/** "Uses your dates and routes. Your stop and weather filters aren't used by this question." */
export function filterUseNote(use: { applied: (keyof typeof FILTER_WORDS)[]; skipped: (keyof typeof FILTER_WORDS)[] }): string {
  const parts: string[] = [];
  if (use.applied.length) parts.push(`Uses your ${joinWords(use.applied.map((f) => FILTER_WORDS[f]))}.`);
  if (use.skipped.length) {
    const n = use.skipped.length === 1 ? "filter isn’t" : "filters aren’t";
    parts.push(`Your ${joinWords(use.skipped.map((f) => FILTER_WORDS[f]))} ${n} used by this question.`);
  }
  return parts.join(" ");
}
