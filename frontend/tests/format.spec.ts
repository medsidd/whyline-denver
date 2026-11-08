import { expect, test } from "@playwright/test";
import { orderColumns, readableDate, readableTimestamp, resultFilename, withoutToday } from "../src/lib/format";

test("result CSV names carry the question and date", () => {
  expect(resultFilename("Worst 10 routes by on-time share", "2026-11-07")).toBe("whylinedenver_worst-10-routes-by-on-time-share_2026-11-07.csv");
  expect(resultFilename("How often do routes run, and which run every 15 minutes all day?", "2026-11-07")).toBe(
    "whylinedenver_how-often-do-routes-run-and-which-run-ev_2026-11-07.csv"
  );
  expect(resultFilename("  ", "2026-11-07")).toBe("whylinedenver_results_2026-11-07.csv");
});

test("dates and update times read as words", () => {
  expect(readableDate("2026-11-07")).toBe("Nov 7, 2026");
  expect(readableDate("2025-10-23")).toBe("Oct 23, 2025");
  expect(readableTimestamp("2026-11-07 17:05 MST")).toBe("Nov 7, 5:05 PM MST");
  expect(readableTimestamp("2026-11-07 00:30 MST")).toBe("Nov 7, 12:30 AM MST");
  expect(readableTimestamp("2026-07-01 18:00 UTC")).toBe("Jul 1, 12:00 PM MDT");
  expect(readableTimestamp("Unavailable")).toBe("Unavailable");
});

test("name columns move next to their IDs", () => {
  expect(orderColumns(["route_id", "avg_pct_on_time", "route_name", "route_long_name"])).toEqual([
    "route_id",
    "route_name",
    "route_long_name",
    "avg_pct_on_time",
  ]);
  expect(orderColumns(["stop_id", "crash_250m_cnt", "lat", "lon", "stop_name"])).toEqual(["stop_id", "stop_name", "crash_250m_cnt", "lat", "lon"]);
  expect(orderColumns(["stop_name", "n"])).toEqual(["stop_name", "n"]);
});

test("today's partial day is left out of trends", () => {
  const rows = [{ d: "2026-11-06", v: 1 }, { d: "2026-11-07", v: 0.2 }];
  expect(withoutToday(rows, "d", "2026-11-07")).toEqual({ rows: [rows[0]], dropped: true });
  expect(withoutToday(rows, "d", "2026-11-08")).toEqual({ rows, dropped: false });
});
