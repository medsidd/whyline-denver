import Image from "next/image";
import Link from "next/link";
import { CENSUS_NOTICE, DOCS, GITHUB, GLOSSARY } from "@/lib/links";

const LINKS: [string, string][] = [
  ["/privacy", "Privacy"],
  ["/terms", "Terms of use"],
  ["/attribution", "Data attribution"],
  [GITHUB, "GitHub"],
  [DOCS, "Technical docs"],
  [GLOSSARY, "Metric definitions"],
];

/** Footer for the landing and legal pages; carries the notices data providers require. */
export function SiteFooter() {
  return (
    <footer className="bg-white">
      <div className="max-w-[1200px] mx-auto py-8 px-[clamp(16px,4vw,48px)] flex flex-col gap-5 text-sm font-semibold text-wl-ink2">
        <div className="flex flex-wrap gap-x-10 gap-y-3 items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Image src="/assets/logo-512.png" alt="" width={26} height={26} />
            <span>
              Unofficial, independent project. Not endorsed by, sponsored by or affiliated with RTD or the City and County
              of Denver.
            </span>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-1">
            {LINKS.map(([href, label]) =>
              href.startsWith("/") ? (
                <Link key={href} href={href} className="py-3 text-wl-navy font-extrabold hover:text-wl-red">
                  {label}
                </Link>
              ) : (
                <a key={href} href={href} className="py-3 text-wl-navy font-extrabold hover:text-wl-red">
                  {label}
                </a>
              )
            )}
          </nav>
        </div>
        <p className="m-0 text-[13px] border-t border-wl-rule pt-5">
          {CENSUS_NOTICE} Weather data from NOAA’s National Centers for Environmental Information. Transit data from RTD’s
          public GTFS feeds. Crash and sidewalk data from the City and County of Denver. © {new Date().getFullYear()} WhyLine
          Denver contributors. Code released under the MIT License.
        </p>
      </div>
    </footer>
  );
}
