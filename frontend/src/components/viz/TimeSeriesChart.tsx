"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { chartColors, chartTheme } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  /** Optional grouping column (route_id or stop_id) — top 5 groups */
  groupKey?: string;
  title?: string;
}

const axes = (xKey: string) => [
  <CartesianGrid key="g" {...chartTheme.grid} />,
  <XAxis key="x" dataKey={xKey} tick={chartTheme.tick} angle={-25} textAnchor="end" axisLine={false} tickLine={false} minTickGap={12} />,
  <YAxis key="y" tick={chartTheme.tick} axisLine={false} tickLine={false} width={56} />,
  <Tooltip key="t" {...chartTheme.tooltip} cursor={{ stroke: "#C9D6E3", strokeWidth: 2 }} />,
];

export function TimeSeriesChart({ data, xKey, yKey, groupKey, title }: Props) {
  const caption = title && <figcaption className="mb-3 font-black text-lg text-wl-navy">{title}</figcaption>;

  // If groupKey present, pivot to grouped line chart (top 5 groups)
  if (groupKey) {
    const groups = Array.from(new Set(data.map((r) => String(r[groupKey])))).slice(0, 5);

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
      <figure className="m-0 w-full">
        {caption}
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
            {axes(xKey)}
            <Legend verticalAlign="top" align="left" iconType="circle" wrapperStyle={{ paddingBottom: 12, fontSize: 13, fontWeight: 800 }}
              formatter={(v) => <span style={{ color: "#042F54" }}>{v}</span>}
            />
            {groups.map((g, i) => (
              <Line key={g} type="monotone" dataKey={g} stroke={chartColors[i % chartColors.length]} dot={false} strokeWidth={2} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </figure>
    );
  }

  const chartData = data.slice(0, 500);
  return (
    <figure className="m-0 w-full">
      {caption}
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
          {axes(xKey)}
          <Line type="monotone" dataKey={yKey} stroke={chartColors[0]} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}
