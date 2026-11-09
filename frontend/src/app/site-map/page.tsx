import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/landing/LegalPage";
import { DOCS, GITHUB, GLOSSARY } from "@/lib/links";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Site Map | WhyLine Denver",
  description: "Every page on WhyLine Denver, its sections, and where the documentation lives.",
  path: "/site-map",
});

const SECTIONS: { heading: string; links: [string, string, string?][] }[] = [
  {
    heading: "Pages",
    links: [
      ["/", "Home", "What WhyLine Denver is and how it works"],
      ["/app", "Dashboard", "Ask a question, check the SQL, see and download the results"],
      ["/privacy", "Privacy policy"],
      ["/terms", "Terms of use"],
      ["/attribution", "Data attribution", "Sources, licenses and required notices"],
    ],
  },
  {
    heading: "On the home page",
    links: [
      ["/#topics", "What you can ask about"],
      ["/#how", "How it works"],
      ["/#limits", "What the numbers mean"],
      ["/#data", "Where the data comes from"],
      ["/#faq", "Questions"],
    ],
  },
  {
    heading: "Documentation",
    links: [
      [GLOSSARY, "Metric definitions", "How each number is calculated, and its limits"],
      [DOCS, "Technical docs", "Pipeline, API and operations"],
      [GITHUB, "Source code on GitHub", "MIT-licensed"],
    ],
  },
  {
    heading: "For search engines",
    links: [
      ["/sitemap.xml", "sitemap.xml"],
      ["/robots.txt", "robots.txt"],
    ],
  },
];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
// Pages render through Next.js links; files and other sites are plain links.
const isPage = (href: string) => href.startsWith("/") && !/\.(xml|txt)$/.test(href);

export default function SiteMapPage() {
  return (
    <LegalPage title="Site map">
      {SECTIONS.map(({ heading, links }) => (
        <section key={heading} aria-labelledby={`map-${slug(heading)}`}>
          <h2 id={`map-${slug(heading)}`}>{heading}</h2>
          <ul>
            {links.map(([href, label, note]) => (
              <li key={href}>
                {isPage(href) ? <Link href={href}>{label}</Link> : <a href={href}>{label}</a>}
                {note && <span className="text-wl-ink2">: {note}</span>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </LegalPage>
  );
}
