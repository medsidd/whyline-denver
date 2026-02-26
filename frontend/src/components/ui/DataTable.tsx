"use client";

import { useState } from "react";
import { tokens } from "@/lib/tokens";

interface Props {
  columns: string[];
  data: Record<string, unknown>[];
  totalRows: number;
  /** Max rows already applied by the API (default 10,000) */
  maxDisplayRows?: number;
}

const PAGE_SIZE = 50;

/** Paginated data table — mirrors st.dataframe in results_viewer.py */
export function DataTable({ columns, data, totalRows, maxDisplayRows = 10_000 }: Props) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(data.length / PAGE_SIZE);
  const pageData = data.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const formatCell = (val: unknown): string => {
    if (val === null || val === undefined) return "";
    if (typeof val === "number") return Number.isInteger(val) ? String(val) : val.toFixed(4);
    return String(val);
  };

  return (
    <div className="w-full">
      {totalRows > maxDisplayRows && (
        <div
          className="mb-3 px-4 py-2 rounded-xl text-sm border"
          style={{
            backgroundColor: `rgba(232, 184, 99, 0.1)`,
            borderColor: tokens.warning,
            color: tokens.warning,
          }}
        >
          ⚠️ Large result set ({totalRows.toLocaleString()} rows). Showing first {maxDisplayRows.toLocaleString()} rows. Download full CSV below.
        </div>
      )}

      {/* Table */}
      <div className="w-full overflow-auto rounded-xl border" style={{ borderColor: tokens.border }}>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr style={{ backgroundColor: tokens.surface }}>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left font-semibold whitespace-nowrap"
                  style={{
                    color: tokens.accent,
                    fontFamily: "var(--font-space-grotesk)",
                    borderBottom: `2px solid ${tokens.border}`,
                    fontSize: "0.8rem",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr
                key={i}
                style={{
                  backgroundColor: i % 2 === 0 ? "transparent" : `rgba(50, 46, 56, 0.4)`,
                }}
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-2 whitespace-nowrap"
                    style={{ color: tokens.text, borderBottom: `1px solid ${tokens.border}` }}
                  >
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs" style={{ color: tokens.muted }}>
            Showing rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.length)} of{" "}
            {data.length.toLocaleString()} displayed
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 rounded-lg text-xs disabled:opacity-40"
              style={{ backgroundColor: tokens.surface, color: tokens.primary, border: `1px solid ${tokens.border}` }}
            >
              ← Prev
            </button>
            <span className="px-3 py-1 text-xs" style={{ color: tokens.muted }}>
              {page + 1} / {pageCount}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page >= pageCount - 1}
              className="px-3 py-1 rounded-lg text-xs disabled:opacity-40"
              style={{ backgroundColor: tokens.surface, color: tokens.primary, border: `1px solid ${tokens.border}` }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
