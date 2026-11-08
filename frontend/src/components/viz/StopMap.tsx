"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import DeckGL from "@deck.gl/react";
import { WebMercatorViewport } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { detectMapMetric } from "@/lib/chartLogic";
import { columnLabel, formatValue } from "@/lib/format";

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

const MAP_HEIGHT = 420;

/** View that fits every point with 40 px padding, at most zoom 14; Denver when there's nothing to fit. */
export function fitView(points: { lat: number; lon: number }[], width: number, height: number) {
  if (!points.length || width < 100) return DENVER_VIEW;
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  const pad = 0.002; // a single point still gets a box to fit
  const { longitude, latitude, zoom } = new WebMercatorViewport({ width, height }).fitBounds(
    [
      [Math.min(...lons) - pad, Math.min(...lats) - pad],
      [Math.max(...lons) + pad, Math.max(...lats) + pad],
    ],
    { padding: 40, maxZoom: 14 }
  );
  return { ...DENVER_VIEW, longitude, latitude, zoom };
}

export function StopMap({ data }: Props) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!isFullscreen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    // Full screen covers the page, so the page behind it shouldn't scroll.
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", handler);
    };
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
  const minVal = metricValues.length ? Math.min(...metricValues) : 0;

  // Fit when the points change; later resizes (full screen, rotation) keep the user's pan and zoom.
  const measured = width > 0;
  const view = useMemo(() => fitView(points, width, MAP_HEIGHT), [points, measured]); // eslint-disable-line react-hooks/exhaustive-deps

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
    : { height: MAP_HEIGHT, position: "relative" };

  return (
    <figure className="m-0">
    <div
      ref={boxRef}
      className={`w-full overflow-hidden ${isFullscreen ? "" : "rounded-[22px]"}`}
      style={containerStyle}
    >
      {/* Mount only once measured: initialViewState is read at mount, and remounting DeckGL mid-init throws. */}
      {width > 0 && (
      <DeckGL
        initialViewState={view}
        controller
        layers={[layer]}
        getTooltip={({ object }) => {
          if (!object) return null;
          const point = object as StopPoint;
          const label = point.stop_name ? `${point.stop_name} (${point.stop_id})` : String(point.stop_id ?? "");
          const metric = metricKey
            ? `${columnLabel(metricKey)}: ${formatValue(metricKey, point[metricKey])}`
            : "";
          return {
            html: `<div style="font:700 13px/1.4 var(--font-nunito),system-ui,sans-serif;color:#4A5F73"><b style="color:#042F54;font-weight:900">${label}</b>${metric ? `<br/>${metric}` : ""}</div>`,
            style: { background: "#FFFFFF", padding: "10px 12px", borderRadius: "14px", boxShadow: "0 12px 32px -12px rgba(4,47,84,.35)" },
          };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>
      )}

      <button
        type="button"
        onClick={() => setIsFullscreen((f) => !f)}
        aria-pressed={isFullscreen}
        className="absolute top-3 right-3 z-[51] h-10 px-4 rounded-full bg-white text-sm font-extrabold text-wl-navy shadow-[0_8px_20px_-8px_rgba(4,47,84,.4)] hover:bg-wl-canvas"
      >
        {isFullscreen ? "Exit full screen" : "Full screen"}
      </button>
    </div>
    {metricKey && metricValues.length > 0 && (
      <figcaption className="mt-2 px-1 flex items-center gap-2 text-[13px] font-bold text-wl-ink2">
        <svg aria-hidden="true" width="34" height="16" viewBox="0 0 34 16">
          <circle cx="5" cy="8" r="3" fill="#D9191C" fillOpacity=".8" stroke="#fff" />
          <circle cx="23" cy="8" r="7" fill="#D9191C" fillOpacity=".8" stroke="#fff" />
        </svg>
        Dot size: {columnLabel(metricKey)}, {formatValue(metricKey, minVal)}–{formatValue(metricKey, maxVal)}
      </figcaption>
    )}
    </figure>
  );
}
