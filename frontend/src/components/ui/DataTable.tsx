"use client";

import { useEffect, useMemo, useState } from "react";
import { columnLabel, formatValue, orderColumns } from "@/lib/format";

interface Props {
  columns: string[];
  data: Record<string, unknown>[];
  totalRows: number;
  /** Max rows already applied by the API (default 10,000) */
  maxDisplayRows?: number;
}

const PAGE_SIZE = 50;

const pageBtn =
  "h-10 px-4 rounded-full bg-wl-canvas text-sm font-extrabold text-wl-navy hover:bg-wl-navy-tint disabled:opacity-40 disabled:hover:bg-wl-canvas";

type Sort = { col: string; dir: "ascending" | "descending" } | null;

/** Order of values for sorting: numbers numerically, everything else as text with numeric runs ("2" < "10"). */
function compare(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "en", { numeric: true });
}

/**
 * Paginated result table; numeric columns are right-aligned. Headers read as words (the raw
 * name is in the tooltip) and sort ascending, descending, then back to the query's order.
 * Name columns sit next to their IDs.
 */
export function DataTable({ columns: rawColumns, data, totalRows, maxDisplayRows = 10_000 }: Props) {
  const columns = useMemo(() => orderColumns(rawColumns), [rawColumns]);
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<Sort>(null);
  useEffect(() => {
    setSort(null);
    setPage(0);
  }, [data]);
  const sorted = useMemo(() => {
    if (!sort) return data;
    const sign = sort.dir === "ascending" ? 1 : -1;
    // Empty values stay last whichever way the column sorts.
    return [...data].sort((a, b) => {
      const ea = a[sort.col] == null || a[sort.col] === "";
      const eb = b[sort.col] == null || b[sort.col] === "";
      if (ea || eb) return Number(ea) - Number(eb);
      return sign * compare(a[sort.col], b[sort.col]);
    });
  }, [data, sort]);
  const pageCount = Math.ceil(data.length / PAGE_SIZE);
  const pageData = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const numeric = new Set(columns.filter((c) => typeof data.find((r) => r[c] != null)?.[c] === "number"));

  const cycleSort = (col: string) => {
    setPage(0);
    setSort((s) =>
      s?.col !== col ? { col, dir: "ascending" } : s.dir === "ascending" ? { col, dir: "descending" } : null
    );
  };

  return (
    <div className="w-full">
      {totalRows > maxDisplayRows && (
        <p className="mt-0 mb-3 px-4 py-2.5 rounded-2xl bg-wl-gold-tint text-sm font-bold text-wl-navy">
          This result has {totalRows.toLocaleString()} rows. The table shows the first {maxDisplayRows.toLocaleString()}.
        </p>
      )}

      <div className="w-full overflow-auto max-h-[560px] rounded-[20px] border-2 border-wl-rule">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0">
            <tr className="bg-wl-canvas">
              {columns.map((col) => (
                <th
                  key={col}
                  scope="col"
                  aria-sort={sort?.col === col ? sort.dir : undefined}
                  className={`p-0 font-black text-wl-navy whitespace-nowrap border-b-2 border-wl-rule ${numeric.has(col) ? "text-right" : "text-left"}`}
                >
                  <button
                    type="button"
                    title={col}
                    onClick={() => cycleSort(col)}
                    className={`w-full px-4 py-3 inline-flex items-center gap-1.5 font-black hover:bg-wl-navy-tint ${numeric.has(col) ? "justify-end" : ""}`}
                  >
                    {col.toLowerCase().endsWith("_id") ? `${columnLabel(col)} ID` : columnLabel(col) || col}
                    <span aria-hidden="true" className={`text-[11px] ${sort?.col === col ? "text-wl-navy" : "text-wl-ink2/40"}`}>
                      {sort?.col === col ? (sort.dir === "ascending" ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr key={i} className="hover:bg-wl-teal-tint/50">
                {columns.map((col) => (
                  <td
                    key={col}
                    className={`px-4 py-2.5 whitespace-nowrap font-semibold text-wl-navy border-b border-wl-rule ${
                      numeric.has(col) ? "text-right tabular-nums" : ""
                    }`}
                  >
                    {formatValue(col, row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
          <span className="text-[13px] font-bold text-wl-ink2">
            Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.length)} of {data.length.toLocaleString()}
          </span>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} className={pageBtn}>
              Previous
            </button>
            <span className="px-1 text-[13px] font-bold text-wl-ink2">
              Page {page + 1} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page >= pageCount - 1}
              className={pageBtn}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
