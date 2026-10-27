"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFilters } from "@/lib/api";
import { defaultFilters, useDashboardStore } from "@/store/dashboardStore";
import { useFreshness } from "@/components/layout/Header";

const WEATHER_LABELS: Record<string, string> = { none: "Dry", rain: "Rain", snow: "Snow" };

const label = "block text-sm font-extrabold text-wl-navy mb-1.5";
const hint = "mt-1.5 text-[13px] font-semibold text-wl-ink2";

/** Filter rail: dates, routes, stop and weather. Collapses behind a toggle below lg. */
export function Sidebar() {
  const { filters, setFilters } = useDashboardStore();
  const freshness = useFreshness();
  const [open, setOpen] = useState(false);
  const [routeDraft, setRouteDraft] = useState("");

  const { data: filterData } = useQuery({
    queryKey: ["filters"],
    queryFn: fetchFilters,
    staleTime: 5 * 60 * 1000,
  });

  const { date_min: min, date_max: max } = filterData ?? {};
  const outOfRange =
    !!min && !!max && !!filters.start_date && !!filters.end_date && (filters.start_date > max || filters.end_date < min);

  const activeCount =
    filters.routes.length + (filters.stop_id.trim() ? 1 : 0) + filters.weather.length;

  const addRoute = (value: string) => {
    const route = (filterData?.routes ?? []).find((r) => r.toLowerCase() === value.trim().toLowerCase());
    if (!route) return false;
    if (!filters.routes.includes(route)) setFilters({ routes: [...filters.routes, route] });
    setRouteDraft("");
    return true;
  };

  const pickLatestWeek = () => {
    if (!max) return;
    const start = new Date(`${max}T00:00:00Z`);
    start.setUTCDate(start.getUTCDate() - 7);
    const iso = start.toISOString().slice(0, 10);
    setFilters({ start_date: min && iso < min ? min : iso, end_date: max });
  };

  return (
    <aside aria-label="Filters" className="lg:sticky lg:top-[88px] lg:max-h-[calc(100vh-104px)] lg:overflow-y-auto rounded-[28px] bg-white wl-shadow">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="wl-filters"
        className="lg:hidden w-full flex items-center justify-between gap-3 min-h-[56px] px-5 font-black text-lg"
      >
        <span>
          Filters
          {activeCount > 0 && <span className="ml-2 text-sm font-extrabold text-wl-teal">{activeCount} active</span>}
        </span>
        <span aria-hidden="true" className={`wl-plus w-8 h-8 rounded-full bg-wl-navy-tint flex items-center justify-center text-xl ${open ? "rotate-45 bg-wl-gold" : ""}`}>
          +
        </span>
      </button>

      <div id="wl-filters" className={`${open ? "flex" : "hidden"} lg:flex flex-col gap-6 p-5 pt-1 lg:pt-6`}>
        <p className="m-0 text-[13px] font-semibold text-wl-ink2">
          These filters are added to the SQL WhyLine writes for your question.
          {/* The header shows this from md up */}
          {/^\d{4}-/.test(freshness) && <span className="md:hidden"> Data updated {freshness}.</span>}
        </p>

        {/* Dates */}
        <fieldset>
          <legend className={label}>Dates</legend>
          <div className="grid gap-2">
            <label className="grid grid-cols-[40px_minmax(0,1fr)] items-center">
              <span className="text-[13px] font-extrabold text-wl-ink2">From</span>
              <input
                type="date"
                value={filters.start_date ?? ""}
                min={min ?? undefined}
                max={max ?? undefined}
                onChange={(e) => setFilters({ start_date: e.target.value || null })}
                className="wl-field"
              />
            </label>
            <label className="grid grid-cols-[40px_minmax(0,1fr)] items-center">
              <span className="text-[13px] font-extrabold text-wl-ink2">To</span>
              <input
                type="date"
                value={filters.end_date ?? ""}
                min={min ?? undefined}
                max={max ?? undefined}
                onChange={(e) => setFilters({ end_date: e.target.value || null })}
                className="wl-field"
              />
            </label>
          </div>
          {outOfRange ? (
            <p role="status" className="mt-2 px-3 py-2.5 rounded-2xl bg-wl-gold-tint text-[13px] font-bold text-wl-navy">
              These dates have no data. Data runs from {min} to {max}.{" "}
              <button type="button" onClick={pickLatestWeek} className="underline font-extrabold">
                Use the latest week
              </button>
            </p>
          ) : (
            min && max && <p className={hint}>Data runs from {min} to {max}.</p>
          )}
        </fieldset>

        {/* Routes */}
        <div>
          <label htmlFor="wl-route" className={label}>
            Routes
          </label>
          <input
            id="wl-route"
            list="wl-route-options"
            value={routeDraft}
            placeholder="Type a route, like 15"
            autoComplete="off"
            onChange={(e) => {
              // Picking from the list fires a change with the exact value
              if (!addRoute(e.target.value)) setRouteDraft(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addRoute(routeDraft);
              }
            }}
            className="wl-field"
          />
          <datalist id="wl-route-options">
            {(filterData?.routes ?? []).map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
          {filters.routes.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {filters.routes.map((r) => (
                <li key={r}>
                  <button
                    type="button"
                    onClick={() => setFilters({ routes: filters.routes.filter((x) => x !== r) })}
                    aria-label={`Remove route ${r}`}
                    className="inline-flex items-center gap-1.5 h-8 pl-3 pr-2 rounded-full bg-wl-teal-tint text-sm font-extrabold text-wl-navy hover:bg-wl-red-tint"
                  >
                    {r}
                    <span aria-hidden="true" className="text-base leading-none text-wl-ink2">×</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={hint}>All routes</p>
          )}
        </div>

        {/* Stop */}
        <div>
          <label htmlFor="wl-stop" className={label}>
            Stop ID
          </label>
          <input
            id="wl-stop"
            type="text"
            inputMode="numeric"
            value={filters.stop_id}
            placeholder="Any stop"
            onChange={(e) => setFilters({ stop_id: e.target.value })}
            className="wl-field"
          />
        </div>

        {/* Weather */}
        <fieldset>
          <legend className={label}>Weather</legend>
          <div className="flex flex-wrap gap-1.5">
            {(filterData?.weather_bins ?? ["none", "rain", "snow"]).map((bin) => {
              const on = filters.weather.includes(bin);
              return (
                <button
                  key={bin}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setFilters({ weather: on ? filters.weather.filter((w) => w !== bin) : [...filters.weather, bin] })
                  }
                  className={`h-9 px-4 rounded-full text-sm font-extrabold transition-colors ${
                    on ? "bg-wl-gold text-wl-navy shadow-[0_3px_0_#B88500]" : "bg-wl-canvas text-wl-navy hover:bg-wl-gold-tint"
                  }`}
                >
                  {WEATHER_LABELS[bin] ?? bin}
                </button>
              );
            })}
          </div>
          {filters.weather.length === 0 && <p className={hint}>Any weather</p>}
        </fieldset>

        <button
          type="button"
          onClick={() => setFilters(defaultFilters())}
          className="self-start h-10 px-4 -ml-1 rounded-full text-sm font-extrabold text-wl-teal hover:bg-wl-teal-tint"
        >
          Reset filters
        </button>
      </div>
    </aside>
  );
}
