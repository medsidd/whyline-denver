"use client";

import { useState } from "react";

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

/** Paginated result table; numeric columns are right-aligned. */
export function DataTable({ columns, data, totalRows, maxDisplayRows = 10_000 }: Props) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(data.length / PAGE_SIZE);
  const pageData = data.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const numeric = new Set(columns.filter((c) => typeof data.find((r) => r[c] != null)?.[c] === "number"));

  const formatCell = (val: unknown): string => {
    if (val === null || val === undefined) return "";
    if (typeof val === "number") return Number.isInteger(val) ? String(val) : val.toFixed(4);
    return String(val);
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
                  className={`px-4 py-3 font-black text-wl-navy whitespace-nowrap border-b-2 border-wl-rule ${numeric.has(col) ? "text-right" : "text-left"}`}
                >
                  {col}
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
                    {formatCell(row[col])}
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
