"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { tokens, chartColors } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  title?: string;
}

export function RouteBarChart({ data, xKey, yKey, title }: Props) {
  const display = data.slice(0, 15);

  return (
    <div className="w-full">
      {title && (
        <p className="text-sm font-semibold mb-3" style={{ color: tokens.accent, fontFamily: "var(--font-space-grotesk)" }}>
          {title}
        </p>
      )}
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={display} margin={{ top: 8, right: 16, left: 0, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} />
          <XAxis
            dataKey={xKey}
            tick={{ fill: tokens.muted, fontSize: 11 }}
            angle={-35}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fill: tokens.muted, fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 8 }}
            labelStyle={{ color: tokens.accent }}
            itemStyle={{ color: tokens.text }}
          />
          <Bar dataKey={yKey} radius={[4, 4, 0, 0]}>
            {display.map((_, i) => (
              <Cell key={i} fill={chartColors[i % chartColors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
