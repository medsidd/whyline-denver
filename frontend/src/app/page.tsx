import type { Metadata } from "next";
import Link from "next/link";
import { tokens } from "@/lib/tokens";

export const metadata: Metadata = {
  title: "WhyLine Denver | Free RTD Transit Analytics Dashboard",
  description:
    "WhyLine Denver — Ask plain-English questions about RTD Denver reliability, delays, equity gaps, safety, and weather impacts. Free, open-source transit analytics.",
};

const FEATURES = [
  {
    icon: "🚌",
    heading: "Bus Reliability (RTD Denver)",
    body: "Which routes are most reliable? When do delays peak? Slice by route, stop, hour, and date.",
  },
  {
    icon: "📊",
    heading: "Equity Gaps",
    body: "Where do vulnerable communities bear the worst service? Access scores layered with Census data.",
  },
  {
    icon: "⚠",
    heading: "Safety Proximity",
    body: "Which bus stops are near high-crash corridors? Identify safety risks along transit routes.",
  },
  {
    icon: "🌦",
    heading: "Weather Impacts",
    body: "Quantify how snow, rain, and fog degrade on-time performance across Denver's RTD network.",
  },
  {
    icon: "📥",
    heading: "Downloadable Data",
    body: "Export any result as CSV or download the full DuckDB warehouse for offline analysis.",
  },
  {
    icon: "🤖",
    heading: "Natural Language to SQL",
    body: "Type a question. Get trusted SQL auto-generated, validated, and ready to run against live data.",
  },
];

const FAQ = [
  {
    q: "What is WhyLine Denver?",
    a: "A free, open-source RTD Denver transit analytics app. Ask questions in plain English and get charts, maps, and downloadable data powered by DuckDB and BigQuery.",
  },
  {
    q: "Does it cover RTD Denver reliability?",
    a: "Yes. Explore on-time performance, delay trends by route, stop, hour of day, and long-term seasonal patterns.",
  },
  {
    q: "Can I analyze transit Denver equity and safety?",
    a: "Yes. Equity scores from Census ACS, crash-proximity from Denver Open Data, and weather from NOAA are all pre-joined and queryable.",
  },
  {
    q: "Is a login or API key required?",
    a: "No login required. The DuckDB engine runs on fast local data. BigQuery requires no user credentials — queries run through the backend.",
  },
];

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "WhyLine Denver",
    url: "https://www.whylinedenver.com",
    logo: "https://www.whylinedenver.com/assets/whylinedenver-logo.svg",
    description:
      "WhyLine Denver turns plain-English questions into trusted RTD transit insights across reliability, delays, safety, weather, and equity.",
    sameAs: [
      "https://github.com/medsidd/whyline-denver",
      "https://medsidd.github.io/whyline-denver/",
    ],
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

export default function LandingPage() {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: tokens.background, color: tokens.text, fontFamily: "var(--font-inter)" }}
    >
      {/* Hero */}
      <header className="retro-banner flex flex-col items-center text-center px-6 py-20">
        <div className="retro-banner__stripe" aria-hidden="true" />

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/assets/whylinedenver-logo.svg"
          alt="WhyLine Denver logo"
          width={96}
          height={96}
          className="mb-6 relative z-10"
          style={{ width: 96, height: 96 }}
        />

        <h1
          className="text-4xl md:text-5xl font-extrabold mb-4 relative z-10"
          style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
        >
          WhyLine Denver
        </h1>
        <p
          className="text-lg md:text-xl max-w-2xl mb-2 relative z-10"
          style={{ color: tokens.text }}
        >
          RTD Transit Analytics — ask anything, get real answers.
        </p>
        <p
          className="text-sm max-w-xl mb-10 relative z-10"
          style={{ color: tokens.muted }}
        >
          Free &amp; open-source. Powered by DuckDB, BigQuery, dbt, and plain-English AI queries.
        </p>

        <Link
          href="/app"
          className="relative z-10 inline-block px-10 py-4 rounded-xl font-bold text-base uppercase tracking-wide transition-all hover:-translate-y-0.5 hover:shadow-xl"
          style={{
            background: `linear-gradient(135deg, ${tokens.accent} 0%, ${tokens.warning} 100%)`,
            color: tokens.surfaceDark,
            fontFamily: "var(--font-space-grotesk)",
            boxShadow: `0 4px 24px rgba(212, 165, 116, 0.4)`,
          }}
        >
          Launch Dashboard
        </Link>
      </header>

      {/* What You Can Analyze */}
      <section className="px-6 py-16 max-w-5xl mx-auto w-full">
        <h2
          className="text-2xl font-bold mb-10 text-center"
          style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
        >
          What You Can Analyze
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(({ icon, heading, body }) => (
            <div
              key={heading}
              className="rounded-xl p-6 border"
              style={{ backgroundColor: tokens.surface, borderColor: tokens.border }}
            >
              <div className="text-3xl mb-3">{icon}</div>
              <h3
                className="font-semibold mb-2"
                style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.text }}
              >
                {heading}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: tokens.muted }}>
                {body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section
        className="px-6 py-16"
        style={{ backgroundColor: tokens.surfaceDark }}
      >
        <div className="max-w-3xl mx-auto text-center">
          <h2
            className="text-2xl font-bold mb-10"
            style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
          >
            How It Works
          </h2>
          <ol className="flex flex-col sm:flex-row gap-8 text-left">
            {[
              { n: "1", title: "Ask a question", desc: "Type anything: Worst 10 routes in snow last 30 days" },
              { n: "2", title: "Review the SQL", desc: "AI generates validated SQL. Edit it in the full CodeMirror editor." },
              { n: "3", title: "Run and explore", desc: "Table, chart, or map. Then download as CSV or DuckDB warehouse." },
            ].map(({ n, title, desc }) => (
              <li key={n} className="flex-1 flex gap-4">
                <span
                  className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm"
                  style={{ backgroundColor: tokens.accent, color: tokens.surfaceDark, fontFamily: "var(--font-space-grotesk)" }}
                >
                  {n}
                </span>
                <div>
                  <p className="font-semibold mb-1" style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.text }}>
                    {title}
                  </p>
                  <p className="text-sm" style={{ color: tokens.muted }}>
                    {desc}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* FAQ */}
      <section className="px-6 py-16 max-w-3xl mx-auto w-full">
        <h2
          className="text-2xl font-bold mb-8 text-center"
          style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.accent }}
        >
          FAQ
        </h2>
        <dl className="flex flex-col gap-6">
          {FAQ.map(({ q, a }) => (
            <div
              key={q}
              className="rounded-xl p-5 border"
              style={{ backgroundColor: tokens.surface, borderColor: tokens.border }}
            >
              <dt
                className="font-semibold mb-2"
                style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.text }}
              >
                {q}
              </dt>
              <dd className="text-sm leading-relaxed" style={{ color: tokens.muted }}>
                {a}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* CTA */}
      <section className="px-6 py-16 text-center">
        <p className="text-lg font-semibold mb-6" style={{ fontFamily: "var(--font-space-grotesk)", color: tokens.text }}>
          Ready to explore Denver transit data?
        </p>
        <Link
          href="/app"
          className="inline-block px-10 py-4 rounded-xl font-bold text-base uppercase tracking-wide transition-all hover:-translate-y-0.5"
          style={{
            background: `linear-gradient(135deg, ${tokens.accent} 0%, ${tokens.warning} 100%)`,
            color: tokens.surfaceDark,
            fontFamily: "var(--font-space-grotesk)",
            boxShadow: `0 4px 24px rgba(212, 165, 116, 0.4)`,
          }}
        >
          Open WhyLine Denver
        </Link>
      </section>

      {/* Footer */}
      <footer
        className="mt-auto px-6 py-8 text-center border-t"
        style={{ borderColor: tokens.border, color: tokens.muted }}
      >
        <p className="text-xs mb-2">
          Data sources: Denver RTD GTFS · Denver Open Data · NOAA Weather · U.S. Census ACS
        </p>
        <p className="text-xs">
          <a
            href="https://github.com/medsidd/whyline-denver"
            className="hover:underline mr-4"
            style={{ color: tokens.primary }}
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <a
            href="https://medsidd.github.io/whyline-denver/"
            className="hover:underline"
            style={{ color: tokens.primary }}
            target="_blank"
            rel="noopener noreferrer"
          >
            Technical Docs
          </a>
        </p>
      </footer>

      {/* JSON-LD structured data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
    </div>
  );
}