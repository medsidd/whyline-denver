"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import DeckGL from "@deck.gl/react";
import { WebMercatorViewport } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { detectMapMetric, routeIdsOf } from "@/lib/chartLogic";
import { fetchRouteShapes } from "@/lib/api";
import type { RouteShape } from "@/types/api";
import { columnLabel, escapeHtml, formatValue } from "@/lib/format";

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

// Route lines: distinct from the red stop dots, and named in the legend under the map.
const ROUTE_COLORS: [number, number, number][] = [
  [10, 127, 160], [217, 154, 0], [53, 87, 184], [125, 140, 31], [4, 47, 84],
  [155, 79, 150], [0, 137, 123], [138, 109, 59], [92, 107, 192], [96, 125, 139],
];
const rgb = ([r, g, b]: [number, number, number]) => `rgb(${r},${g},${b})`;
const TOOLTIP_STYLE = { background: "#FFFFFF", padding: "10px 12px", borderRadius: "14px", boxShadow: "0 12px 32px -12px rgba(4,47,84,.35)" };

/** View that fits every [lon, lat] with 40 px padding, at most zoom 14; Denver when there's nothing to fit. */
export function fitView(coords: [number, number][], width: number, height: number) {
  if (!coords.length || width < 100) return DENVER_VIEW;
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
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
    // The box only renders once there are points to show.
  }, [data.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Routes the result names are drawn under the stops (a stop-only result has none).
  const routeIds = useMemo(() => routeIdsOf(data), [data]);
  const { data: rawShapes, isFetched: shapesSettled, isError: shapesFailed } = useQuery({
    queryKey: ["route-shapes", routeIds.join(",")],
    queryFn: () => fetchRouteShapes(routeIds),
    enabled: routeIds.length > 0,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
  // Only well-formed [lon, lat] paths reach the map: a malformed one would break fitting and drawing.
  const shapes = useMemo(
    () => (rawShapes ?? []).filter((s) => s.path.length >= 2 && s.path.every((c) => Number.isFinite(c[0]) && Number.isFinite(c[1]))),
    [rawShapes]
  );
  const colorOf = (routeId: string) => ROUTE_COLORS[Math.max(0, routeIds.indexOf(routeId)) % ROUTE_COLORS.length];
  const routeNames = useMemo(() => {
    const names: Record<string, string> = {};
    const key = Object.keys(data[0] ?? {}).find((c) => c.toLowerCase() === "route_id") ?? "route_id";
    for (const r of data) {
      const id = r[key] == null ? "" : String(r[key]);
      const name = [r.route_long_name, r.route_name].map((v) => (v ? String(v) : "")).find((v) => v && v !== id);
      if (id && name && !names[id]) names[id] = name;
    }
    return names;
  }, [data]);
  const drawn = routeIds.filter((id) => shapes.some((s) => s.route_id === id));

  // Fit to the stops; a route-only result fits its lines, and waits for them before mounting the map.
  // Lines arriving later never refit, so a user's pan and zoom survive (as do resizes).
  const measured = width > 0;
  const routeOnly = points.length === 0;
  const view = useMemo(
    () => fitView(routeOnly ? shapes.flatMap((s) => s.path) : points.map((p) => [p.lon, p.lat] as [number, number]), width, MAP_HEIGHT),
    [points, routeOnly ? shapes : null, measured] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const routeLayer = new PathLayer<RouteShape>({
    id: "routes",
    data: shapes,
    getPath: (d) => d.path,
    getColor: (d) => [...colorOf(d.route_id), 220],
    getWidth: 4,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    pickable: true,
  });

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

  if (points.length === 0 && routeIds.length === 0) return null;
  if (routeOnly && (shapesFailed || (shapesSettled && drawn.length === 0))) {
    return (
      <p className="m-0 px-5 py-4 rounded-[22px] bg-wl-canvas text-[15px] font-bold text-wl-ink2">
        No route lines are available for these routes right now, and the result has no stop locations to map.
      </p>
    );
  }

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
      {width > 0 && (!routeOnly || shapesSettled) && (
      <DeckGL
        initialViewState={view}
        controller
        layers={[routeLayer, layer]}
        getTooltip={({ object }) => {
          if (!object) return null;
          if ("path" in object) {
            const route = object as RouteShape;
            const name = routeNames[route.route_id];
            return {
              html: `<div style="font:900 13px/1.4 var(--font-nunito),system-ui,sans-serif;color:#042F54">Route ${escapeHtml(route.route_id)}${name ? ` · ${escapeHtml(name)}` : ""}</div>`,
              style: TOOLTIP_STYLE,
            };
          }
          const point = object as StopPoint;
          // Result values are user-controlled (custom SQL): escape before they become HTML
          const label = escapeHtml(point.stop_name ? `${point.stop_name} (${point.stop_id})` : String(point.stop_id ?? ""));
          const metric = metricKey
            ? escapeHtml(`${columnLabel(metricKey)}: ${formatValue(metricKey, point[metricKey])}`)
            : "";
          return {
            html: `<div style="font:700 13px/1.4 var(--font-nunito),system-ui,sans-serif;color:#4A5F73"><b style="color:#042F54;font-weight:900">${label}</b>${metric ? `<br/>${metric}` : ""}</div>`,
            style: TOOLTIP_STYLE,
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
    {drawn.length > 0 && (
      <ul aria-label="Routes on the map" className="mt-2 mb-0 px-1 p-0 list-none flex flex-wrap gap-x-4 gap-y-1.5 text-[13px] font-bold text-wl-ink2">
        {drawn.map((id) => (
          <li key={id} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block w-5 h-1.5 rounded-full" style={{ background: rgb(colorOf(id)) }} />
            <span className="text-wl-navy font-extrabold">{id}</span>
            {routeNames[id] && <span>{routeNames[id]}</span>}
          </li>
        ))}
      </ul>
    )}
    {routeIds.length > drawn.length && shapes.length > 0 && (
      <p className="mt-1.5 mb-0 px-1 text-[13px] font-semibold text-wl-ink2">
        No line available for route {routeIds.filter((id) => !drawn.includes(id)).join(", ")}.
      </p>
    )}
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
