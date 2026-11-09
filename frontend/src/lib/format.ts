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

const joinWords = (w: string[]) => (w.length < 2 ? w.join("") : `${w.slice(0, -1).join(", ")} and ${w[w.length - 1]}`);

/**
 * "Uses your dates and routes. Your stop and weather filters aren't used by this question."
 * A filter in both lists had some invalid values left out.
 */
export function filterUseNote(use: { applied: string[]; skipped: string[] }): string {
  // The rail labels the weather filter "Precipitation".
  const word = (f: string) => (f === "weather" ? "precipitation" : f);
  use = { applied: use.applied.map(word), skipped: use.skipped.map(word) };
  const parts: string[] = [];
  const partial = use.skipped.filter((f) => use.applied.includes(f));
  const unused = use.skipped.filter((f) => !use.applied.includes(f));
  if (use.applied.length) parts.push(`Uses your ${joinWords(use.applied)}.`);
  if (partial.length) parts.push(`Some of your ${joinWords(partial)} weren’t valid and were left out.`);
  if (unused.length) parts.push(`Your ${joinWords(unused)} ${unused.length === 1 ? "filter isn’t" : "filters aren’t"} used by this question.`);
  return parts.join(" ");
}

/** Today's date in Denver as YYYY-MM-DD. */
const DENVER_DAY = new Intl.DateTimeFormat("en-US", { timeZone: "America/Denver", year: "numeric", month: "2-digit", day: "2-digit" });

export function denverDate(d: Date = new Date()): string {
  // formatToParts, not an en-CA string: locale data has changed that format before.
  const p = Object.fromEntries(DENVER_DAY.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}

/** "whylinedenver_worst-10-routes-by-on-time-share_2026-11-07.csv"; the slug is cut to 40 characters. */
export function resultFilename(question: string, date: string): string {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 40)
    .replace(/^-+|-+$/g, "");
  return `whylinedenver_${slug || "results"}_${date}.csv`;
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

/** "2026-11-07" -> "Nov 7, 2026" (a calendar date, so no time-zone shift). */
export function readableDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return isNaN(d.getTime()) ? iso : DATE_FMT.format(d);
}

const MT_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

/**
 * API freshness strings to "Nov 7, 5:05 PM MST". Accepts "2026-11-07 17:05 MST" (already
 * Denver time) and "2026-11-07 20:05 UTC"; anything else ("Loading…", "Unavailable") passes through.
 */
export function readableTimestamp(raw: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})\s*(MST|MDT|UTC)$/.exec(raw?.trim() ?? "");
  if (!m) return raw;
  const [, y, mo, d, h, mi, zone] = m;
  if (zone === "UTC") {
    const p = Object.fromEntries(MT_PARTS.formatToParts(new Date(`${y}-${mo}-${d}T${h}:${mi}Z`)).map((x) => [x.type, x.value]));
    return `${p.month} ${p.day}, ${p.hour}:${p.minute} ${p.dayPeriod} ${p.timeZoneName}`;
  }
  const hour = Number(h);
  const month = DATE_FMT.format(new Date(`${y}-${mo}-${d}T00:00:00Z`)).replace(/, \d{4}$/, "");
  return `${month}, ${hour % 12 || 12}:${mi} ${hour < 12 ? "AM" : "PM"} ${zone}`;
}

const NAME_AFTER: Record<string, string[]> = {
  stop_id: ["stop_name"],
  route_id: ["route_name", "route_long_name"],
  from_stop_id: ["from_stop_name"],
  to_stop_id: ["to_stop_name"],
};

/** Moves name columns (which the API often appends at the end) next to their ID column. */
export function orderColumns(columns: string[]): string[] {
  const moved = new Set(
    Object.entries(NAME_AFTER).flatMap(([id, names]) => (columns.includes(id) ? names.filter((n) => columns.includes(n)) : []))
  );
  return columns.flatMap((c) => {
    if (moved.has(c)) return [];
    return [c, ...(NAME_AFTER[c] ?? []).filter((n) => moved.has(n))];
  });
}

/** Rows without today's Denver date in `dateKey`: today is still being collected, so a trend line would dip. */
export function withoutToday<T extends Record<string, unknown>>(rows: T[], dateKey: string, today = denverDate()) {
  const kept = rows.filter((r) => String(r[dateKey] ?? "").slice(0, 10) !== today);
  // A result of only today keeps it: an empty chart would say less.
  return kept.length && kept.length < rows.length ? { rows: kept, dropped: true } : { rows, dropped: false };
}

/** Text for an HTML string (map tooltips are HTML): result values can hold markup. */
export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** Whether SQL reads the live views (LIVE_MARTS in src/whyline/sync/constants.py). */
export function isLiveSql(sql: string): boolean {
  return /\bmart_(vehicles_now|stop_visits_recent)\b/i.test(sql);
}
