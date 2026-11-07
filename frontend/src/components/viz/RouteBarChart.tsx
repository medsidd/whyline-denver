"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { axisTick, formatValue } from "@/lib/format";
import { chartColors, chartTheme } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  title?: string;
  /** Ranked categories read best as horizontal bars; hours stay vertical. */
  orientation?: "horizontal" | "vertical";
  labelOf?: (row: Record<string, unknown>) => string;
}

const MAX_BARS = 25;
const ROW_PX = 28;
const truncate = (s: string, n = 24) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** One-line category label, truncated, with the full text on hover. Recharts' own tick would wrap. */
function CategoryTick({ x, y, payload }: { x: number; y: number; payload: { value: string } }) {
  const full = String(payload.value);
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fill={chartTheme.tick.fill} fontSize={chartTheme.tick.fontSize} fontWeight={chartTheme.tick.fontWeight}>
      <title>{full}</title>
      {truncate(full)}
    </text>
  );
}

export function RouteBarChart({ data, xKey, yKey, title, orientation = "vertical", labelOf }: Props) {
  const display = data.slice(0, MAX_BARS).map((row) => ({ ...row, __label: labelOf ? labelOf(row) : String(row[xKey] ?? "") }));
  const tooltip = (
    <Tooltip
      {...chartTheme.tooltip}
      formatter={(v) => formatValue(yKey, v)}
      labelFormatter={(l) => String(l)}
      cursor={{ fill: "rgba(4,47,84,.05)" }}
    />
  );

  return (
    <figure className="m-0 w-full">
      {title && <figcaption className="mb-3 font-black text-lg text-wl-navy">{title}</figcaption>}
      {orientation === "horizontal" ? (
        <ResponsiveContainer width="100%" height={display.length * ROW_PX + 40}>
          <BarChart data={display} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 4 }} barCategoryGap={4}>
            <CartesianGrid {...chartTheme.grid} vertical horizontal={false} />
            <XAxis type="number" tick={chartTheme.tick} tickFormatter={axisTick(yKey)} axisLine={false} tickLine={false} />
            <YAxis
              type="category"
              dataKey="__label"
              tick={CategoryTick}
              width={180}
              interval={0}
              axisLine={false}
              tickLine={false}
            />
            {tooltip}
            <Bar dataKey={yKey} fill={chartColors[0]} radius={[0, 4, 4, 0]} maxBarSize={20} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={display} margin={{ top: 8, right: 8, left: 0, bottom: 48 }} barCategoryGap={2}>
            <CartesianGrid {...chartTheme.grid} />
            <XAxis dataKey="__label" tick={chartTheme.tick} angle={-35} textAnchor="end" interval={0} axisLine={false} tickLine={false} />
            <YAxis tick={chartTheme.tick} tickFormatter={axisTick(yKey)} axisLine={false} tickLine={false} width={56} />
            {tooltip}
            <Bar dataKey={yKey} fill={chartColors[0]} radius={[4, 4, 0, 0]} maxBarSize={44} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </figure>
  );
}
