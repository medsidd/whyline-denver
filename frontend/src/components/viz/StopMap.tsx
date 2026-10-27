"use client";

import { useMemo, useState, useEffect } from "react";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { detectMapMetric } from "@/lib/chartLogic";

// Denver center coordinates (same as Pydeck default in charts.py)
const DENVER_VIEW = {
  longitude: -104.9903,
  latitude: 39.7392,
  zoom: 11,
  pitch: 0,
  bearing: 0,
};

// Free light map style (no token required), quiet enough for red stop markers
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

interface StopPoint {
  stop_id?: string;
  stop_name?: string;
  lat: number;
  lon: number;
  [key: string]: unknown;
}

interface Props {
  data: Record<string, unknown>[];
}

export function StopMap({ data }: Props) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isFullscreen) setIsFullscreen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isFullscreen]);

  const columns = Object.keys(data[0] ?? {});
  const metricKey = detectMapMetric(columns);

  // Filter to valid coordinates, limit to 500 points (mirrors build_map)
  const points: StopPoint[] = useMemo(() => {
    return data
      .filter((r) => {
        const lat = Number(r.lat);
        const lon = Number(r.lon);
        return !isNaN(lat) && !isNaN(lon) && lat !== 0 && lon !== 0;
      })
      .slice(0, 500)
      .map((r) => ({
        ...r,
        lat: Number(r.lat),
        lon: Number(r.lon),
      })) as StopPoint[];
  }, [data]);

  // Compute radius scale (mirrors Pydeck radius in build_map)
  const metricValues = metricKey
    ? points.map((p) => Number(p[metricKey] ?? 0)).filter((v) => !isNaN(v))
    : [];
  const maxVal = metricValues.length ? Math.max(...metricValues) : 1;

  const layer = new ScatterplotLayer<StopPoint>({
    id: "stops",
    data: points,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: (d) => {
      if (!metricKey) return 5;
      const val = Number(d[metricKey] ?? 0);
      return Math.max(3, Math.min(14, (val / maxVal) * 11 + 3));
    },
    getFillColor: [217, 25, 28, 200],
    stroked: true,
    getLineColor: [255, 255, 255, 255],
    lineWidthMinPixels: 1.5,
    pickable: true,
    autoHighlight: true,
    highlightColor: [4, 47, 84, 230],
    radiusUnits: "pixels",
  });

  if (points.length === 0) return null;

  const containerStyle: React.CSSProperties = isFullscreen
    ? { position: "fixed", inset: 0, zIndex: 50, background: "#F4F8FB" }
    : { height: 420, position: "relative" };

  return (
    <div
      className={`w-full overflow-hidden ${isFullscreen ? "" : "rounded-[22px]"}`}
      style={containerStyle}
    >
      <DeckGL
        initialViewState={DENVER_VIEW}
        controller
        layers={[layer]}
        getTooltip={({ object }) => {
          if (!object) return null;
          const point = object as StopPoint;
          const label = point.stop_name ? `${point.stop_name} (${point.stop_id})` : String(point.stop_id ?? "");
          const metric = metricKey
            ? `${metricKey}: ${Number(point[metricKey] ?? 0).toFixed(2)}`
            : "";
          return {
            html: `<div style="font:700 13px/1.4 var(--font-nunito),system-ui,sans-serif;color:#4A5F73"><b style="color:#042F54;font-weight:900">${label}</b>${metric ? `<br/>${metric}` : ""}</div>`,
            style: { background: "#FFFFFF", padding: "10px 12px", borderRadius: "14px", boxShadow: "0 12px 32px -12px rgba(4,47,84,.35)" },
          };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      <button
        type="button"
        onClick={() => setIsFullscreen((f) => !f)}
        aria-pressed={isFullscreen}
        className="absolute top-3 right-3 z-[51] h-10 px-4 rounded-full bg-white text-sm font-extrabold text-wl-navy shadow-[0_8px_20px_-8px_rgba(4,47,84,.4)] hover:bg-wl-canvas"
      >
        {isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
      </button>
    </div>
  );
}
