"use client";

import { tokens } from "@/lib/tokens";

/** Footer — mirrors branding.py::render_footer() */
export function Footer() {
  return (
    <footer className="text-center py-8 text-sm" style={{ color: tokens.muted }}>
      <hr className="section-separator mb-8" />
      <p className="mb-2">
        <strong style={{ color: tokens.primary }}>WhyLine Denver</strong>
        {" — Built with "}
        <span style={{ color: tokens.accent }}>♥</span>
        {" by your Denver City neighbor."}
      </p>
      <p className="mb-2 text-xs">
        Data sources:{" "}
        <a
          href="https://www.rtd-denver.com/open-records"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.primary }}
        >
          RTD GTFS
        </a>{" "}
        •{" "}
        <a
          href="https://www.denvergov.org/opendata/terms"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.primary }}
        >
          Denver Open Data
        </a>{" "}
        •{" "}
        <a
          href="https://www.ncei.noaa.gov/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.primary }}
        >
          NOAA
        </a>{" "}
        •{" "}
        <a
          href="https://www.census.gov/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.primary }}
        >
          U.S. Census
        </a>
      </p>
      <p className="text-xs mb-0">
        <a
          href="https://github.com/medsidd/whyline-denver"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.accent }}
        >
          View on GitHub
        </a>{" "}
        •{" "}
        <a
          href="https://medsidd.github.io/whyline-denver/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          style={{ color: tokens.accent }}
        >
          dbt Docs
        </a>
      </p>
    </footer>
  );
}
