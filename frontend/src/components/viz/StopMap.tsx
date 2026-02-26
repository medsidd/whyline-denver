"use client";

import { useMemo, useState, useEffect } from "react";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { tokens, rgbaTokens } from "@/lib/tokens";
import { detectMapMetric } from "@/lib/chartLogic";

// Denver center coordinates (same as Pydeck default in charts.py)
const DENVER_VIEW = {
  longitude: -104.9903,
  latitude: 39.7392,
  zoom: 11,
  pitch: 0,
  bearing: 0,
};

// Free dark map style (no token required — same visual as mapbox dark-v10)
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

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
    getFillColor: rgbaTokens.error.concat([160]) as [number, number, number, number],
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 120],
    radiusUnits: "pixels",
  });

  if (points.length === 0) return null;

  const containerStyle: React.CSSProperties = isFullscreen
    ? { position: "fixed", inset: 0, zIndex: 50, background: tokens.surfaceDark }
    : { height: 260, position: "relative", borderColor: tokens.border };

  return (
    <div
      className={`w-full overflow-hidden border${isFullscreen ? " border-0 rounded-none" : " rounded-xl"}`}
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
            html: `<div style="font-size:12px;color:#e8d5c4;background:#322e38;padding:8px;border-radius:6px">
              <b>${label}</b>${metric ? `<br/>${metric}` : ""}
            </div>`,
          };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      {/* Fullscreen toggle button */}
      <button
        onClick={() => setIsFullscreen((f) => !f)}
        title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
        style={{
          position: "absolute",
          top: 8,
          right: 8,
          zIndex: 51,
          padding: "4px 8px",
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 600,
          background: "rgba(50,46,56,0.85)",
          color: tokens.muted,
          border: `1px solid ${tokens.border}`,
          cursor: "pointer",
        }}
      >
        {isFullscreen ? "✕ Exit" : "⛶ Fullscreen"}
      </button>
    </div>
  );
}
