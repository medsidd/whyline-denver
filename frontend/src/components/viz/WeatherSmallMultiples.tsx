"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { tokens, chartColors } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  title?: string;
}

/**
 * Weather small multiples — mirrors the Altair faceted chart in charts.py.
 * One LineChart per weather (precip_bin) condition.
 */
export function WeatherSmallMultiples({ data, title }: Props) {
  const bins = Array.from(new Set(data.map((r) => String(r.precip_bin))));

  return (
    <div className="w-full">
      {title && (
        <p className="text-sm font-semibold mb-3" style={{ color: tokens.accent, fontFamily: "var(--font-space-grotesk)" }}>
          {title}
        </p>
      )}
      <div className="grid grid-cols-2 gap-4">
        {bins.map((bin, i) => {
          const binData = data
            .filter((r) => String(r.precip_bin) === bin)
            .sort((a, b) => String(a.service_date_mst).localeCompare(String(b.service_date_mst)))
            .slice(0, 200);

          return (
            <div key={bin}>
              <p className="text-xs font-semibold mb-1" style={{ color: chartColors[i % chartColors.length] }}>
                {bin}
              </p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={binData} margin={{ top: 4, right: 8, left: 0, bottom: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} />
                  <XAxis dataKey="service_date_mst" tick={{ fill: tokens.muted, fontSize: 9 }} angle={-25} textAnchor="end" />
                  <YAxis domain={[0, 100]} tick={{ fill: tokens.muted, fontSize: 9 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 6 }}
                    labelStyle={{ color: tokens.accent, fontSize: 11 }}
                    itemStyle={{ color: tokens.text, fontSize: 11 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="pct_on_time"
                    stroke={chartColors[i % chartColors.length]}
                    dot={false}
                    strokeWidth={1.5}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>
    </div>
  );
}
