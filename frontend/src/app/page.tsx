import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ScrollRoute } from "@/components/landing/ScrollRoute";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { DOCS, GITHUB, GLOSSARY } from "@/lib/links";
import type { FreshnessResponse } from "@/types/api";

export const metadata: Metadata = {
  title: "WhyLine Denver | Free RTD Transit Analytics Dashboard",
  description:
    "WhyLine Denver — Ask plain-English questions about RTD Denver reliability, delays, equity gaps, safety, and weather impacts. Free, open-source transit analytics.",
};

// Re-render hourly even if the freshness fetch failed at build time.
export const revalidate = 3600;


const askHref = (q: string) => `/app?q=${encodeURIComponent(q)}`;

const CHIPS = [
  { q: "Worst 10 routes, last 30 days", tint: "bg-wl-teal-tint", dot: "bg-wl-teal" },
  { q: "Stops with the most crashes nearby", tint: "bg-wl-red-tint", dot: "bg-wl-red" },
  { q: "Where snow hurts reliability most", tint: "bg-wl-gold-tint", dot: "bg-wl-gold" },
  { q: "Equity gaps", tint: "bg-wl-navy-tint", dot: "bg-wl-navy" },
];

const TOPICS = [
  {
    name: "Reliability",
    line: "bg-wl-teal",
    tint: "bg-wl-teal-tint",
    body: "On-time share and bus spacing by route, stop and hour of day.",
    example: "Which hours have the most late arrivals on route 15?",
    source: "From RTD GTFS schedules and GTFS-Realtime",
  },
  {
    name: "Weather",
    line: "bg-wl-gold",
    tint: "bg-wl-gold-tint",
    body: "How on-time performance shifts on days with rain or snow.",
    example: "Do snowy days lower on-time performance on route 0?",
    source: "From NOAA daily observations at Denver International Airport",
  },
  {
    name: "Safety",
    line: "bg-wl-red",
    tint: "bg-wl-red-tint",
    body: "Reported traffic crashes within 250 meters of each stop.",
    example: "Which stops have the most crashes nearby?",
    source: "From Denver Open Data crash records",
  },
  {
    name: "Equity and access",
    line: "bg-wl-navy",
    tint: "bg-wl-navy-tint",
    body: "Where weak service overlaps with neighborhoods that rely on transit, and how much sidewalk is near each stop.",
    example: "Which high-need stops have the least sidewalk around them?",
    source: "From U.S. Census ACS 2023 and Denver’s sidewalk inventory",
  },
];

const STEPS = [
  { title: "Ask", body: "Type a question, or pick a ready-made one. Date, route and stop filters narrow it down." },
  { title: "Check the SQL", body: "WhyLine writes the query and shows it to you. Edit it if you like. Only read-only queries on approved tables can run." },
  { title: "Explore and download", body: "See the result as a table, chart or map. Download it as CSV, or download a whole table." },
];

const LIMITS = [
  {
    title: "Observed, not complete",
    body: "Reliability counts stop visits seen in vehicle positions, but some trips go unseen and older dates come from 15-minute samples. Treat on-time shares as estimates.",
    icon: <g fill="#F0B616" stroke="none"><circle cx="6" cy="16" r="2.5" /><circle cx="12" cy="9" r="2.5" /><circle cx="18" cy="13" r="2.5" /></g>,
  },
  {
    title: "A day behind",
    body: "Realtime data is collected through the day, but the dashboard reads a nightly snapshot. It’s not a live arrivals board.",
    icon: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></>,
  },
  {
    title: "Context, not cause",
    body: "Crashes near a stop don’t mean transit caused them. Census figures describe areas, not individual riders.",
    icon: <><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><path d="M12 8v3M12 13.5h.01" /></>,
  },
];

const SOURCES = [
  { name: "RTD GTFS schedules", body: "Routes, stops, trips and timetables.", tint: "bg-wl-teal-tint", dot: "bg-wl-teal" },
  { name: "RTD GTFS-Realtime", body: "Trip updates and vehicle positions, read every 15 seconds.", tint: "bg-wl-teal-tint", dot: "bg-wl-teal" },
  { name: "Denver Open Data", body: "Reported traffic crashes and the city’s sidewalk inventory.", tint: "bg-wl-red-tint", dot: "bg-wl-red" },
  { name: "NOAA daily weather", body: "Precipitation, snow and temperature at Denver International Airport.", tint: "bg-wl-gold-tint", dot: "bg-wl-gold" },
  { name: "U.S. Census ACS", body: "2023 five-year estimates for Denver County census tracts.", tint: "bg-wl-navy-tint", dot: "bg-wl-navy" },
];

const FAQ = [
  { q: "Do I need an account?", a: "No. Open the dashboard and start asking." },
  {
    q: "Is this official RTD data?",
    a: "It’s built from RTD’s public feeds, but WhyLine Denver is an independent project, not an RTD service.",
  },
  {
    q: "Can I plan a trip or see live arrivals?",
    a: "No. WhyLine is for looking at how service has performed. It has no trip planner, live arrivals, passenger counts, fares, crowding or service alerts.",
  },
  {
    q: "What happens to my question?",
    a: "It’s sent to Google’s Gemini service to write the SQL. Our logs keep only a one-way hash of it, not the text, and your browser remembers your last question and query until you clear them. The privacy policy has the details.",
  },
  {
    q: "Can I use the data elsewhere?",
    a: "Yes. Download any result, or a whole table, as CSV. The code is MIT-licensed on GitHub. Check each source’s terms before redistributing its data.",
  },
];

// Hero schematic: one line per topic, all running through a shared interchange.
const MAP_LINES = [
  { color: "#0D657F", d: "M110 30 V139 L170 199 H350 L410 139 H500" },
  { color: "#F0B616", d: "M20 213 H500" },
  { color: "#D9191C", d: "M20 227 H430 L490 287 V420" },
  { color: "#042F54", d: "M110 420 V301 L170 241 H350 L390 281 V420" },
];
const MAP_STOPS = [
  [110, 64, 1], [450, 139, 2], [64, 213, 1], [468, 213, 3],
  [140, 227, 2], [490, 360, 4], [110, 380, 3], [390, 372, 4],
];

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "WhyLine Denver",
    url: "https://www.whylinedenver.com",
    logo: "https://www.whylinedenver.com/assets/logo-512.png",
    description:
      "WhyLine Denver turns plain-English questions into trusted RTD transit insights across reliability, delays, safety, weather, and equity.",
    sameAs: [GITHUB, DOCS],
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map(({ q, a }) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: a },
    })),
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "WhyLine Denver",
    url: "https://www.whylinedenver.com/",
    inLanguage: "en-US",
  },
];

/** Dashboard snapshot time from the API; null hides the label rather than showing a guess. */
async function getSnapshot(): Promise<string | null> {
  const base = process.env.API_BASE_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/api/freshness`, {
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    const { bigquery_freshness } = (await res.json()) as FreshnessResponse;
    return bigquery_freshness && bigquery_freshness !== "Unavailable" ? bigquery_freshness : null;
  } catch {
    return null;
  }
}

const h2 = "m-0 font-black text-[clamp(32px,3.6vw,48px)] leading-[1.1] tracking-[-0.03em] text-wl-navy";
const lede = "mt-3 text-[19px] text-wl-ink2 max-w-[60ch]";

function PlusIcon() {
  return (
    <span aria-hidden="true" className="wl-plus flex-none w-9 h-9 rounded-full bg-wl-navy-tint flex items-center justify-center">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#042F54" strokeWidth="3" strokeLinecap="round">
        <path d="M12 5v14M5 12h14" />
      </svg>
    </span>
  );
}

export default async function LandingPage() {
  const snapshot = await getSnapshot();

  return (
    <div id="top" className="wl min-h-screen bg-wl-canvas text-wl-navy font-rounded text-[17px] leading-[1.55] font-medium">
      <header className="wl-nav sticky top-0 z-30 border-b border-wl-navy/[0.08]">
        <div className="max-w-[1200px] mx-auto px-[clamp(16px,4vw,48px)]">
          <nav aria-label="Main" className="h-16 flex items-center gap-3 sm:gap-6">
            <Link href="/" className="flex items-center gap-2 sm:gap-2.5 min-h-[44px] no-underline text-wl-navy">
              <Image src="/assets/logo-512.png" alt="" width={36} height={36} priority />
              <span className="font-black text-[17px] sm:text-xl tracking-[-0.01em] whitespace-nowrap">WhyLine Denver</span>
            </Link>
            <div className="hidden lg:flex gap-1 ml-auto text-[15px] font-bold">
              {[
                ["#topics", "What you can ask"],
                ["#how", "How it works"],
                ["#data", "Data"],
                ["#faq", "FAQ"],
              ].map(([href, label]) => (
                <a key={href} href={href} className="px-3.5 py-2.5 rounded-full text-wl-ink2 hover:text-wl-navy hover:bg-wl-navy-tint">
                  {label}
                </a>
              ))}
              <a href={GITHUB} className="px-3.5 py-2.5 rounded-full text-wl-ink2 hover:text-wl-navy hover:bg-wl-navy-tint">
                GitHub
              </a>
            </div>
            <Link
              href="/app"
              className="wl-btn wl-btn-navy ml-auto lg:ml-0 inline-flex items-center h-11 px-4 sm:px-[22px] rounded-full bg-wl-navy text-white font-extrabold text-sm sm:text-[15px] whitespace-nowrap"
            >
              Open dashboard
            </Link>
          </nav>
          <ScrollRoute />
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-[clamp(16px,4vw,48px)]">
        {/* Hero */}
        <section aria-labelledby="hero-title" className="pt-16 pb-8 flex flex-wrap gap-x-14 gap-y-12 items-center">
          <div className="flex-[1_1_480px] min-w-0">
            <h1 id="hero-title" className="m-0 font-black text-[clamp(44px,6vw,80px)] leading-[1.02] tracking-[-0.035em] text-wl-navy max-w-[11ch]">
              Ask how Denver’s buses are really running.
            </h1>
            <p className="mt-6 text-[clamp(17px,1.5vw,20px)] text-wl-ink2 max-w-[52ch]">
              Ask about RTD service in plain English. WhyLine writes the SQL, shows it to you before it runs, and gives you
              a table, chart or map to download. Free and open source.
            </p>

            <form
              action="/app"
              method="get"
              className="wl-ask mt-8 flex items-center gap-2 max-w-[600px] bg-white rounded-full py-2 pr-2 pl-6 wl-shadow"
            >
              <label htmlFor="wl-q" className="sr-only">
                Your question about Denver transit
              </label>
              <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0D657F" strokeWidth="2.5" strokeLinecap="round" className="flex-none">
                <circle cx="11" cy="11" r="7" />
                <path d="M20 20l-3.5-3.5" />
              </svg>
              <input
                id="wl-q"
                name="q"
                type="text"
                required
                autoComplete="off"
                placeholder="Which routes were least on time last month?"
                className="flex-1 min-w-0 h-[52px] border-0 bg-transparent text-[17px] font-semibold text-wl-navy placeholder:text-[#6B7E90]"
              />
              <button
                type="submit"
                className="wl-btn wl-btn-red flex-none h-[52px] px-[30px] rounded-full bg-wl-red text-white font-black text-[17px] cursor-pointer"
              >
                Ask
              </button>
            </form>

            <div className="mt-[22px] flex flex-wrap items-center gap-2.5">
              <span className="text-sm font-bold text-wl-ink2 mr-0.5">Or start with</span>
              {CHIPS.map(({ q, tint, dot }) => (
                <Link
                  key={q}
                  href={askHref(q)}
                  className={`wl-chip inline-flex items-center gap-2 min-h-[44px] px-4 rounded-full ${tint} text-wl-navy text-sm font-extrabold`}
                >
                  <span aria-hidden="true" className={`w-2.5 h-2.5 rounded-full ${dot}`} />
                  {q}
                </Link>
              ))}
            </div>

            {snapshot && (
              <p className="mt-6 flex items-center gap-2 text-sm font-semibold text-wl-ink2">
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" className="flex-none">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" />
                </svg>
                <span>Dashboard data refreshes nightly. Last snapshot: {snapshot}</span>
              </p>
            )}
          </div>

          <figure className="flex-[1_1_380px] min-w-0 max-w-[540px] m-0 relative">
            <div aria-hidden="true" className="wl-sun absolute left-[12%] right-[12%] top-[2%] aspect-square rounded-full bg-[#FFE9A8]" />
            <svg
              role="img"
              aria-label="Schematic map: four colored lines, one for each topic, run through a shared interchange labeled Your question."
              viewBox="0 0 520 440"
              className="relative w-full h-auto block"
            >
              {MAP_LINES.map(({ d }, i) => (
                <path key={`c${i}`} className="wl-case wl-draw" pathLength={1} d={d} style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
              {MAP_LINES.map(({ d, color }, i) => (
                <path key={`l${i}`} className="wl-line wl-draw" pathLength={1} d={d} stroke={color} style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
              {MAP_STOPS.map(([cx, cy, wave]) => (
                <circle key={`${cx}-${cy}`} className="wl-stop wl-pop" cx={cx} cy={cy} r={8} style={{ animationDelay: `${1 + wave * 0.1}s` }} />
              ))}
              <g className="wl-pop" style={{ animationDelay: "1.55s" }}>
                <rect x="239" y="182" width="42" height="76" rx="21" fill="#FFFFFF" stroke="#042F54" strokeWidth="5" />
                <rect x="188" y="276" width="144" height="40" rx="20" fill="#042F54" />
                <text x="260" y="302" textAnchor="middle" fill="#FFFFFF" fontWeight={900} fontSize={17}>
                  Your question
                </text>
              </g>
            </svg>
            <figcaption className="relative mt-2 text-sm font-semibold text-wl-ink2 max-w-[44ch]">
              Four topics share one dataset, so a single question can cross all of them.
            </figcaption>
          </figure>
        </section>

        {/* Topics */}
        <section id="topics" aria-labelledby="topics-title" className="pt-24">
          <h2 id="topics-title" className={h2}>What you can ask about</h2>
          <p className={lede}>Each topic is a line on the map. Ask within one, or ask a question that rides across several.</p>
          <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-6">
            {TOPICS.map((t) => (
              <article key={t.name} className="wl-card wl-reveal wl-shadow bg-white rounded-[32px] p-7">
                <div aria-hidden="true" className="relative h-6 w-[120px]">
                  <div className={`absolute inset-x-0 top-1.5 h-3 rounded-md ${t.line}`} />
                  <div className="absolute left-12 top-0 w-6 h-6 rounded-full bg-white border-4 border-wl-navy" />
                </div>
                <h3 className="mt-5 mb-0 font-black text-[28px] leading-[1.15] tracking-[-0.02em] text-wl-navy">{t.name}</h3>
                <p className="mt-2">{t.body}</p>
                <p className={`mt-[18px] inline-block py-3 px-[18px] rounded-[22px] rounded-bl-md ${t.tint} font-bold text-[15px]`}>
                  “{t.example}”
                </p>
                <p className="mt-[18px] text-sm font-semibold text-wl-ink2">{t.source}</p>
              </article>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how" aria-labelledby="how-title" className="pt-28">
          <h2 id="how-title" className={h2}>How it works</h2>
          <p className={lede}>Nothing runs until you’ve seen the query.</p>
          <div className="mt-10 flex flex-wrap gap-x-14 gap-y-10 items-start">
            <ol className="flex-[1_1_340px] min-w-0 m-0 p-0 list-none">
              {STEPS.map(({ title, body }, i) => {
                const isLast = i === STEPS.length - 1;
                return (
                  <li key={title} className="wl-reveal flex gap-5">
                    <div aria-hidden="true" className="flex-none w-12 flex flex-col items-center">
                      <div
                        className={`w-12 h-12 rounded-full flex items-center justify-center font-black text-xl ${
                          isLast ? "bg-wl-red text-white shadow-[0_4px_0_#A80F12]" : "bg-wl-gold text-wl-navy shadow-[0_4px_0_#B88500]"
                        }`}
                      >
                        {i + 1}
                      </div>
                      {!isLast && <div className="flex-1 min-h-[40px] mt-2 border-l-4 border-dotted border-[#9FB3C6]" />}
                    </div>
                    <div className={`pt-2 ${isLast ? "" : "pb-9"}`}>
                      <h3 className="m-0 font-black text-2xl leading-[1.2] text-wl-navy">{title}</h3>
                      <p className="mt-1.5 text-wl-ink2 max-w-[44ch]">{body}</p>
                    </div>
                  </li>
                );
              })}
            </ol>

            <figure className="wl-reveal flex-[1_1_480px] min-w-0 m-0 bg-wl-navy rounded-[32px] overflow-hidden shadow-[0_30px_60px_-30px_rgba(4,47,84,0.6)]">
              <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 py-[18px] px-[22px]">
                <span className="font-black text-base text-white">Worst 10 routes, last 30 days</span>
                <span className="inline-flex items-center gap-1.5 h-8 pl-2.5 pr-3.5 rounded-full bg-white/10 text-[13px] font-extrabold text-white">
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F0B616" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  Read-only check passed
                </span>
              </figcaption>
              {/* Same SQL as the first prebuilt query in api/routers/sql.py */}
              <pre className="mx-2.5 mb-2.5 mt-0 p-5 rounded-3xl bg-wl-navy-deep overflow-x-auto text-sm leading-[1.75] text-[#E6EEF5]" style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
                <code>
                  <K>SELECT</K> route_id, <K>AVG</K>(pct_on_time) <K>AS</K> avg_pct_on_time{"\n"}
                  <K>FROM</K> <span className="text-[#7FD0E6]">mart_reliability_by_route_day</span>{"\n"}
                  <K>WHERE</K> service_date_mst &gt;= <K>DATE_SUB</K>(<K>CURRENT_DATE</K>, <K>INTERVAL</K> <N>30</N> <K>DAY</K>){"\n"}
                  <K>GROUP BY</K> route_id{"\n"}
                  <K>ORDER BY</K> avg_pct_on_time <K>ASC</K>{"\n"}
                  <K>LIMIT</K> <N>10</N>
                </code>
              </pre>
            </figure>
          </div>
        </section>

        {/* Limits */}
        <section id="limits" aria-labelledby="limits-title" className="pt-28">
          <div className="wl-reveal bg-wl-gold-tint rounded-[40px] p-[clamp(28px,4vw,56px)]">
            <h2 id="limits-title" className={h2}>What the numbers mean</h2>
            <p className={lede}>Read these before you quote a result.</p>
            <div className="mt-9 grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-x-9 gap-y-7">
              {LIMITS.map(({ title, body, icon }) => (
                <div key={title}>
                  <LimitIcon>{icon}</LimitIcon>
                  <h3 className="mt-3.5 mb-0 font-black text-[21px] leading-[1.25] text-wl-navy">{title}</h3>
                  <p className="mt-1.5 text-base text-wl-ink2">{body}</p>
                </div>
              ))}
              <div>
                <LimitIcon>
                  <circle cx="12" cy="12" r="8" />
                  <path d="M12 11v5M12 8h.01" />
                </LimitIcon>
                <h3 className="mt-3.5 mb-0 font-black text-[21px] leading-[1.25] text-wl-navy">Independent</h3>
                <p className="mt-1.5 text-base text-wl-ink2">
                  WhyLine Denver is not an official RTD or City of Denver service.{" "}
                  <a href={GLOSSARY} className="text-wl-navy font-extrabold underline">
                    Read the metric definitions
                  </a>
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Data sources */}
        <section id="data" aria-labelledby="data-title" className="pt-28">
          <h2 id="data-title" className={h2}>Where the data comes from</h2>
          <p className={lede}>Public sources, collected on a schedule and joined in one warehouse.</p>
          <ul className="wl-reveal wl-shadow mt-9 p-2 list-none bg-white rounded-[32px]">
            {SOURCES.map(({ name, body, tint, dot }, i) => (
              <li key={name} className={`flex items-center gap-4 py-4 px-[18px] ${i ? "border-t border-wl-rule" : ""}`}>
                <span aria-hidden="true" className={`flex-none w-11 h-11 rounded-full ${tint} flex items-center justify-center`}>
                  <span className={`w-3.5 h-3.5 rounded-full ${dot}`} />
                </span>
                <span className="flex-1 min-w-0">
                  <strong className="font-black">{name}</strong>
                  <span className="block text-wl-ink2 text-[15px]">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>

        {/* FAQ */}
        <section id="faq" aria-labelledby="faq-title" className="pt-28">
          <h2 id="faq-title" className={h2}>Questions</h2>
          <div className="mt-8 max-w-[820px] flex flex-col gap-3">
            {FAQ.map(({ q, a }) => (
              <details key={q} className="wl-faq bg-white rounded-[28px] px-6 shadow-[0_2px_0_rgba(4,47,84,0.04)]">
                <summary className="flex justify-between items-center gap-4 min-h-[68px] font-extrabold text-lg text-wl-navy">
                  {q}
                  <PlusIcon />
                </summary>
                <p className="mt-0 mb-[22px] text-wl-ink2 max-w-[64ch]">{a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* Closing CTA */}
        <section id="cta" aria-labelledby="cta-title" className="pt-28 pb-24">
          <div className="wl-reveal relative overflow-hidden bg-wl-navy rounded-[44px] p-[clamp(36px,6vw,80px)]">
            <div aria-hidden="true" className="absolute -right-20 -bottom-40 w-[420px] h-[420px] rounded-full bg-wl-gold" />
            <div aria-hidden="true" className="absolute -right-10 -bottom-[120px] w-[340px] h-[340px] rounded-full bg-[#F5C63E]" />
            <div className="relative max-w-[640px]">
              <h2 id="cta-title" className="m-0 font-black text-[clamp(36px,5vw,64px)] leading-[1.04] tracking-[-0.035em] text-white">
                Start with a question.
              </h2>
              <p className="mt-4 text-[19px] font-semibold text-[#C9D6E3]">No account needed.</p>
              <div className="mt-8 flex flex-wrap gap-3.5">
                <Link
                  href="/app"
                  className="wl-btn wl-btn-gold inline-flex items-center h-14 px-[30px] rounded-full bg-wl-gold text-wl-navy font-black text-[17px]"
                >
                  Open dashboard
                </Link>
                <a
                  href={GITHUB}
                  className="wl-btn inline-flex items-center h-14 px-7 rounded-full border-2 border-white/50 text-white font-extrabold text-[17px] hover:bg-white/10"
                >
                  View the code
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />

      {/* JSON-LD structured data */}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </div>
  );
}

function LimitIcon({ children }: { children: React.ReactNode }) {
  return (
    <div aria-hidden="true" className="w-[52px] h-[52px] rounded-full bg-wl-navy flex items-center justify-center">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#F0B616" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
        {children}
      </svg>
    </div>
  );
}

const K = ({ children }: { children: React.ReactNode }) => <span className="text-wl-gold">{children}</span>;
const N = ({ children }: { children: React.ReactNode }) => <span className="text-[#FF9C8F]">{children}</span>;
