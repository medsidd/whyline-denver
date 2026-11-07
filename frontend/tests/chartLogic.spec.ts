import { expect, test } from "@playwright/test";
import { barColumns, detectChartType, hourColumns, labelOf, orderByColumn } from "../src/lib/chartLogic";
import { columnLabel, filterUseNote, humanBytes } from "../src/lib/format";

const EQUITY_SQL = "SELECT stop_id, stop_name, priority_score, vuln_score_0_100, crash_score_0_100,\n  reliability_score_0_100, lat, lon\nFROM mart_priority_hotspots\nWHERE reliability_score_0_100 IS NOT NULL\nORDER BY priority_score DESC\nLIMIT 20";

test("equity charts the priority score it ranks by, labelled by stop name", () => {
  const columns = ["stop_id", "stop_name", "priority_score", "vuln_score_0_100", "crash_score_0_100", "reliability_score_0_100", "lat", "lon"];
  const row = { stop_id: "22368", stop_name: "16th St & Stout", priority_score: 68.3, vuln_score_0_100: 90, crash_score_0_100: 50, reliability_score_0_100: 40, lat: 39.7, lon: -104.9 };
  expect(barColumns(columns, EQUITY_SQL, [row])).toEqual({ category: "stop_name", metric: "priority_score" });
  expect(detectChartType(columns, EQUITY_SQL, [row])).toBe("generic_bar");
});

test("slow segments are labelled from → to and chart the speed", () => {
  const sql = "SELECT s.route_id, s.direction_id, s.from_stop_name, s.to_stop_name, s.hour_mst,\n  s.p50_speed_kmh FROM mart_segment_speed_by_hour s ORDER BY s.p50_speed_kmh ASC";
  const columns = ["route_id", "direction_id", "from_stop_name", "to_stop_name", "hour_mst", "p50_speed_kmh", "delay_ratio", "n_traversals", "lat", "lon"];
  const row = { route_id: "15", direction_id: 0, from_stop_name: "Colfax & Broadway", to_stop_name: "Colfax & Lincoln", hour_mst: 17, p50_speed_kmh: 6.1, delay_ratio: 1.4, n_traversals: 40, lat: 0, lon: 0 };
  const cols = barColumns(columns, sql, [row]);
  expect(cols).toEqual({ category: "from_stop_name", metric: "p50_speed_kmh" });
  expect(labelOf(columns, cols!.category)(row)).toBe("17:00 Colfax & Broadway → Colfax & Lincoln");
  expect(hourColumns(columns, sql, [row])).toBeNull();
});

test("crash exposure is labelled by stop name", () => {
  const sql = "SELECT stop_id, stop_name, crash_250m_cnt, lat, lon FROM mart_crash_proximity_by_stop ORDER BY crash_250m_cnt DESC";
  const columns = ["stop_id", "stop_name", "crash_250m_cnt", "lat", "lon"];
  expect(barColumns(columns, sql, [{ stop_id: "1", stop_name: "A", crash_250m_cnt: 9, lat: 1, lon: 2 }])).toEqual({ category: "stop_name", metric: "crash_250m_cnt" });
});

test("a metric by hour gets an hour chart; ignoring lat/lon and booleans", () => {
  const columns = ["hour_mst", "avg_pct_on_time"];
  expect(detectChartType(columns, "SELECT hour_mst, AVG(pct_on_time) AS avg_pct_on_time FROM t GROUP BY 1 ORDER BY hour_mst", [{ hour_mst: 7, avg_pct_on_time: 0.8 }])).toBe("hour_bar");
  expect(hourColumns(columns)).toEqual({ hour: "hour_mst", metric: "avg_pct_on_time" });
  // ORDER BY a boolean falls back to the first metric-like numeric column
  const freq = ["route_id", "is_frequent_route", "headway_midday_min"];
  expect(barColumns(freq, "SELECT * FROM t ORDER BY is_frequent_route DESC", [{ route_id: "15", is_frequent_route: true, headway_midday_min: 10 }])).toBeNull();
});

test("route labels add the long name when it differs, and the method when grouped by it", () => {
  const label = labelOf(["route_id", "route_name", "route_long_name", "method"], "route_id");
  expect(label({ route_id: "15", route_name: "15", route_long_name: "East Colfax", method: "sampled" })).toBe("15 East Colfax (sampled)");
  expect(labelOf(["route_id", "route_name"], "route_id")({ route_id: "AL", route_name: "AL" })).toBe("AL");
});

test("route bars without a SQL keep the old keyword match", () => {
  expect(barColumns(["route_id", "avg_pct_on_time"])).toEqual({ category: "route_id", metric: "avg_pct_on_time" });
  expect(orderByColumn("select a from t order by s.b desc")).toBe("b");
});

test("column labels read as words", () => {
  expect(columnLabel("vuln_score_0_100")).toBe("Vulnerability score (0–100)");
  expect(columnLabel("crash_250m_cnt")).toBe("Number of crashes within 250 m");
  expect(columnLabel("avg_pct_on_time")).toBe("Average % on time");
  expect(columnLabel("priority_score")).toBe("Priority score");
  expect(columnLabel("p50_speed_kmh")).toBe("Median speed (km/h)");
});

test("scan sizes use 1000-based units and filter notes read as sentences", () => {
  expect(humanBytes(2_000_000_000)).toBe("2 GB");
  expect(humanBytes(42_651_597)).toBe("42.65 MB");
  expect(filterUseNote({ applied: ["dates", "routes"], skipped: ["stop", "weather"] })).toBe(
    "Uses your dates and routes. Your stop and weather filters aren’t used by this question."
  );
  expect(filterUseNote({ applied: [], skipped: ["dates"] })).toBe("Your dates filter isn’t used by this question.");
  expect(filterUseNote({ applied: ["routes"], skipped: ["routes"] })).toBe("Uses your routes. Some of your routes weren’t valid and were left out.");
});

test("hour columns are hour-of-day only, and a null first row doesn't hide the ORDER BY metric", () => {
  expect(hourColumns(["route_id", "avg_hours_late"])).toBeNull();
  expect(barColumns(["route_id", "avg_hours_late"])).toEqual({ category: "route_id", metric: "avg_hours_late" });
  expect(hourColumns(["day_of_week", "trips_per_hour"])).toBeNull();
  expect(hourColumns(["event_hour_mst", "pct_on_time"])).toEqual({ hour: "event_hour_mst", metric: "pct_on_time" });
  const rows = [{ route_id: "A", metric: null }, { route_id: "B", metric: 0.4 }];
  expect(barColumns(["route_id", "metric"], "SELECT * FROM t ORDER BY metric", rows)).toEqual({ category: "route_id", metric: "metric" });
});
