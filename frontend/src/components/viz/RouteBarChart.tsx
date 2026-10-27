"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { chartColors, chartTheme } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  title?: string;
}

export function RouteBarChart({ data, xKey, yKey, title }: Props) {
  const display = data.slice(0, 15);

  return (
    <figure className="m-0 w-full">
      {title && <figcaption className="mb-3 font-black text-lg text-wl-navy">{title}</figcaption>}
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={display} margin={{ top: 8, right: 8, left: 0, bottom: 48 }} barCategoryGap={2}>
          <CartesianGrid {...chartTheme.grid} />
          <XAxis dataKey={xKey} tick={chartTheme.tick} angle={-35} textAnchor="end" interval={0} axisLine={false} tickLine={false} />
          <YAxis tick={chartTheme.tick} axisLine={false} tickLine={false} width={56} />
          <Tooltip {...chartTheme.tooltip} cursor={{ fill: "rgba(4,47,84,.05)" }} />
          <Bar dataKey={yKey} fill={chartColors[0]} radius={[4, 4, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
