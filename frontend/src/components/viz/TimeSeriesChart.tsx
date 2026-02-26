"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { tokens, chartColors } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  /** Optional grouping column (route_id or stop_id) — top 5 groups */
  groupKey?: string;
  title?: string;
}

export function TimeSeriesChart({ data, xKey, yKey, groupKey, title }: Props) {
  // If groupKey present, pivot to grouped line chart (top 5 groups)
  if (groupKey) {
    const groups = [
      ...new Set(data.map((r) => String(r[groupKey]))),
    ].slice(0, 5);

    // Pivot: { [date]: { [group]: value } }
    const pivoted: Record<string, Record<string, unknown>> = {};
    for (const row of data) {
      const xVal = String(row[xKey]);
      if (!pivoted[xVal]) pivoted[xVal] = { [xKey]: xVal };
      const group = String(row[groupKey]);
      if (groups.includes(group)) {
        pivoted[xVal][group] = row[yKey];
      }
    }
    const chartData = Object.values(pivoted).slice(0, 500);

    return (
      <div className="w-full">
        {title && <p className="text-sm font-semibold mb-3" style={{ color: tokens.accent }}>{title}</p>}
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} />
            <XAxis dataKey={xKey} tick={{ fill: tokens.muted, fontSize: 11 }} angle={-25} textAnchor="end" />
            <YAxis tick={{ fill: tokens.muted, fontSize: 11 }} />
            <Tooltip
              contentStyle={{ backgroundColor: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 8 }}
              labelStyle={{ color: tokens.accent }}
              itemStyle={{ color: tokens.text }}
            />
            <Legend wrapperStyle={{ color: tokens.muted, fontSize: 12 }} />
            {groups.map((g, i) => (
              <Line
                key={g}
                type="monotone"
                dataKey={g}
                stroke={chartColors[i % chartColors.length]}
                dot={false}
                strokeWidth={2}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const chartData = data.slice(0, 500);
  return (
    <div className="w-full">
      {title && <p className="text-sm font-semibold mb-3" style={{ color: tokens.accent }}>{title}</p>}
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} />
          <XAxis dataKey={xKey} tick={{ fill: tokens.muted, fontSize: 11 }} angle={-25} textAnchor="end" />
          <YAxis domain={[0, 100]} tick={{ fill: tokens.muted, fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 8 }}
            labelStyle={{ color: tokens.accent }}
            itemStyle={{ color: tokens.text }}
          />
          <Line type="monotone" dataKey={yKey} stroke={tokens.primary} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
