"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { chartColors, chartTheme } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  title?: string;
}

const small = { ...chartTheme.tick, fontSize: 11 };

/**
 * Weather small multiples — one line chart per precipitation bin, all in one
 * hue on a shared 0–1 on-time scale; the facet title carries identity.
 */
export function WeatherSmallMultiples({ data, title }: Props) {
  const bins = Array.from(new Set(data.map((r) => String(r.precip_bin))));

  return (
    <figure className="m-0 w-full">
      {title && <figcaption className="mb-3 font-black text-lg text-wl-navy">{title}</figcaption>}
      <div className="grid sm:grid-cols-2 gap-4">
        {bins.map((bin) => {
          const binData = data
            .filter((r) => String(r.precip_bin) === bin)
            .sort((a, b) => String(a.service_date_mst).localeCompare(String(b.service_date_mst)))
            .slice(0, 200);

          return (
            <div key={bin} className="rounded-[18px] bg-wl-canvas p-3">
              <p className="m-0 mb-1 text-sm font-black text-wl-navy capitalize">{bin}</p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={binData} margin={{ top: 4, right: 8, left: 0, bottom: 24 }}>
                  <CartesianGrid {...chartTheme.grid} stroke="#D6E0EA" />
                  <XAxis dataKey="service_date_mst" tick={small} angle={-25} textAnchor="end" axisLine={false} tickLine={false} minTickGap={12} />
                  <YAxis domain={[0, 1]} tick={small} axisLine={false} tickLine={false} width={40} />
                  <Tooltip {...chartTheme.tooltip} cursor={{ stroke: "#C9D6E3", strokeWidth: 2 }} />
                  <Line type="monotone" dataKey="pct_on_time" stroke={chartColors[0]} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
