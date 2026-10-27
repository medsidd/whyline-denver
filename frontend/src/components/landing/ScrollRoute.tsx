"use client";

import { useEffect, useRef, useState } from "react";

const ROUTE_STOPS = [
  { id: "top", label: "Start" },
  { id: "topics", label: "What you can ask" },
  { id: "how", label: "How it works" },
  { id: "limits", label: "What the numbers mean" },
  { id: "data", label: "Where the data comes from" },
  { id: "faq", label: "Questions" },
  { id: "cta", label: "Open the dashboard" },
];

// One logo color per stop; the road after a stop and the next-stop sign share it.
const COLORS = ["#0D657F", "#F0B616", "#D9191C", "#042F54", "#0D657F", "#F0B616", "#D9191C"];
const HEADER_OFFSET = 150;
const EPS = 0.003;
const LAST = ROUTE_STOPS.length - 1;

const pos = (v: number) => `calc(22px + (100% - 44px) * ${v.toFixed(4)})`;

/** Route bar under the landing header: a bus drives along it in sync with page scroll. */
export function ScrollRoute() {
  const [p, setP] = useState(0);
  const [y, setY] = useState(0);
  const [dir, setDir] = useState<1 | -1>(1);
  const [moving, setMoving] = useState(false);
  const [at, setAt] = useState(() => ROUTE_STOPS.map((_, i) => i / LAST));
  const lastY = useRef(0);

  useEffect(() => {
    let frame = 0;
    let idle: ReturnType<typeof setTimeout>;
    const maxScroll = () => Math.max(1, document.documentElement.scrollHeight - window.innerHeight);

    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sy = window.scrollY;
        if (sy !== lastY.current) setDir(sy > lastY.current ? 1 : -1);
        lastY.current = sy;
        setY(sy);
        setP(Math.min(1, Math.max(0, sy / maxScroll())));
        setMoving(true);
        clearTimeout(idle);
        idle = setTimeout(() => setMoving(false), 160);
      });
    };
    // A stop sits where its section reaches the top of the viewport, under the sticky header.
    const measure = () => {
      const max = maxScroll();
      setAt(
        ROUTE_STOPS.map(({ id }, i) => {
          const el = document.getElementById(id);
          if (!el) return i / LAST;
          const top = el.getBoundingClientRect().top + window.scrollY - HEADER_OFFSET;
          return Math.min(1, Math.max(0, top / max));
        })
      );
      onScroll();
    };

    lastY.current = window.scrollY;
    measure();
    document.fonts?.ready.then(measure);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(idle);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", measure);
    };
  }, []);

  let current = 0;
  at.forEach((v, i) => {
    if (p >= v - EPS) current = i;
  });
  let next: string;
  if (dir === 1) {
    next = current < LAST ? ROUTE_STOPS[current + 1].label : "End of the line";
  } else {
    let prev = -1;
    at.forEach((v, i) => {
      if (v < p - EPS) prev = i;
    });
    next = prev >= 0 ? ROUTE_STOPS[prev].label : "Start";
  }
  const signBg = COLORS[current];
  const signFg = signBg === "#F0B616" ? "#042F54" : "#FFFFFF";

  return (
    <div className="flex items-center gap-5 pb-1.5">
      <nav aria-label="Page sections" className="relative h-14 flex-1 min-w-0">
        <div aria-hidden="true" className="absolute left-[22px] right-[22px] top-[38px] h-1.5 rounded bg-wl-road" />
        {ROUTE_STOPS.slice(0, LAST).map(({ id }, i) => (
          <div
            key={id}
            aria-hidden="true"
            className="absolute top-[38px] h-1.5 rounded"
            style={{
              left: pos(at[i]),
              width: `calc((100% - 44px) * ${Math.max(0, Math.min(p, at[i + 1]) - at[i]).toFixed(4)})`,
              background: COLORS[i],
            }}
          />
        ))}
        {ROUTE_STOPS.map(({ id, label }, i) => (
          <a
            key={id}
            href={`#${id}`}
            aria-label={`Go to ${label}`}
            className={`wl-stopbtn ${i === current ? "is-current" : ""}`}
            style={{ left: pos(at[i]) }}
          >
            <span className="wl-dot" style={{ background: at[i] <= p + EPS ? COLORS[i] : "#FFFFFF" }} />
            <span className={`wl-tip ${i === 0 ? "is-start" : i === LAST ? "is-end" : ""}`} aria-hidden="true">
              {label}
            </span>
          </a>
        ))}
        <div
          aria-hidden="true"
          className="absolute top-[11px] md:top-1 z-[3] pointer-events-none w-12 h-[29px] md:w-[60px] md:h-9 -translate-x-1/2"
          style={{ left: pos(p) }}
        >
          <div className="wl-busflip w-full h-full" style={{ transform: `scaleX(${dir})` }}>
            <Bus moving={moving} wheel={Math.round(y * 0.9)} />
          </div>
        </div>
      </nav>
      <p
        className="wl-nextstop hidden md:flex flex-none items-center gap-2 h-9 pl-3 pr-4 m-0 rounded-full text-sm font-extrabold min-w-[250px]"
        style={{ background: signBg, color: signFg }}
      >
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
          <circle cx="12" cy="9.5" r="2.5" />
        </svg>
        <span>
          <span className="font-bold">Next stop:</span> {next}
        </span>
      </p>
    </div>
  );
}

function Bus({ moving, wheel }: { moving: boolean; wheel: number }) {
  const wheelAt = (cx: number) => (
    <g style={{ transformOrigin: `${cx}px 28px`, transform: `rotate(${wheel}deg)` }}>
      <circle cx={cx} cy="28" r="6.5" fill="#042F54" />
      <circle cx={cx} cy="28" r="2.6" fill="#FFFFFF" />
      <rect x={cx - 1} y="22.5" width="2" height="3.5" rx="1" fill="#FFFFFF" />
    </g>
  );
  return (
    <svg className={`wl-bus block w-full h-full overflow-visible ${moving ? "is-moving" : ""}`} viewBox="0 0 60 36">
      <rect x="2" y="2" width="55" height="25" rx="9" fill="#F0B616" stroke="#042F54" strokeWidth="2.5" />
      <rect x="8" y="7" width="9" height="9" rx="3" fill="#042F54" />
      <rect x="20" y="7" width="9" height="9" rx="3" fill="#042F54" />
      <rect x="32" y="7" width="9" height="9" rx="3" fill="#042F54" />
      <rect x="44" y="7" width="10" height="12" rx="3.5" fill="#0D657F" stroke="#042F54" strokeWidth="2" />
      <rect x="3.5" y="19" width="38" height="3.5" rx="1.75" fill="#D9191C" />
      <circle cx="55" cy="22.5" r="1.8" fill="#FFFFFF" />
      {wheelAt(15)}
      {wheelAt(45)}
    </svg>
  );
}
