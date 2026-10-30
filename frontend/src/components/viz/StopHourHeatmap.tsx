"use client";

import { tokens } from "@/lib/tokens";

interface Props {
  data: Record<string, unknown>[];
  title?: string;
  maxStops?: number;
}

/** On-time share by stop (rows) and hour (columns); rows repeated across dates are averaged. */
export function StopHourHeatmap({ data, title, maxStops = 15 }: Props) {
  const cells = new Map<string, { sum: number; n: number }>();
  const stops: string[] = [];
  const names = new Map<string, string>();
  const hours = new Set<number>();
  for (const row of data) {
    const stop = String(row.stop_id ?? "");
    const hour = Number(row.event_hour_mst);
    const value = Number(row.pct_on_time);
    if (!stop || !Number.isFinite(hour) || row.pct_on_time == null || !Number.isFinite(value)) continue;
    if (!names.has(stop)) {
      if (stops.length >= maxStops) continue;
      stops.push(stop);
      names.set(stop, String(row.stop_name ?? stop));
    }
    hours.add(hour);
    const key = `${stop}|${hour}`;
    const cell = cells.get(key) ?? { sum: 0, n: 0 };
    cell.sum += value;
    cell.n += 1;
    cells.set(key, cell);
  }
  const hourList = [...hours].sort((a, b) => a - b);
  if (!stops.length || !hourList.length) return null;
  // Stretch the colour ramp over the shares actually shown, so a 75–100% spread stays readable.
  const shares = [...cells.values()].map((c) => c.sum / c.n);
  const lo = Math.min(...shares);
  const span = Math.max(...shares) - lo || 1;

  return (
    <figure className="m-0 w-full">
      {title && <figcaption className="mb-3 font-black text-lg text-wl-navy">{title}</figcaption>}
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-xs font-bold">
          <thead>
            <tr>
              <th scope="col" className="text-left pr-2 text-wl-ink2 font-extrabold">Stop</th>
              {hourList.map((h) => (
                <th key={h} scope="col" className="w-9 text-center text-wl-ink2 font-extrabold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stops.map((stop) => (
              <tr key={stop}>
                <th scope="row" className="text-left pr-2 max-w-[220px] truncate font-bold text-wl-navy">
                  {names.get(stop)}
                </th>
                {hourList.map((h) => {
                  const cell = cells.get(`${stop}|${h}`);
                  if (!cell) return <td key={h} className="w-9 h-7 bg-wl-canvas" aria-label="no data" />;
                  const share = cell.sum / cell.n;
                  const pct = Math.round(share * 100);
                  // Darker teal = more on time.
                  const alpha = 0.15 + 0.85 * ((share - lo) / span);
                  return (
                    <td
                      key={h}
                      title={`${names.get(stop)}, ${h}:00: ${pct}% on time`}
                      className="w-9 h-7 text-center rounded"
                      style={{ background: `rgba(10,127,160,${alpha})`, color: alpha > 0.55 ? tokens.white : tokens.navy }}
                    >
                      {pct}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 mb-0 text-xs font-semibold text-wl-ink2">
        Percent of visits on time, by hour of day. Darker is more on time, from {Math.round(lo * 100)}% to{" "}
        {Math.round((lo + span) * 100)}% here; grey cells have no data.
      </p>
    </figure>
  );
}
