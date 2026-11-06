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
};

/** "avg_pct_on_time" -> "Average % on time", "route_id" -> "Route". */
export function columnLabel(col: string): string {
  const s = col
    .toLowerCase()
    .split("_")
    .map((w) => WORDS[w] ?? w)
    .filter(Boolean)
    .join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
