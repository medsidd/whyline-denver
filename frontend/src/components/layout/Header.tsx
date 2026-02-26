"use client";

/** Retro banner header — mirrors branding.py::render_header() */
export function Header() {
  return (
    <header className="retro-banner">
      <div className="retro-banner__stripe" />
      {/* Logo */}
      <div className="flex-shrink-0 flex items-center justify-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/assets/whylinedenver-logo.svg"
          alt="WhyLine Denver logo"
          className="retro-banner__logo-img"
          onError={(e) => {
            // Fallback to PNG if SVG not found
            (e.target as HTMLImageElement).src = "/assets/whylinedenver-logo@512.png";
          }}
        />
      </div>
      {/* Title + tagline */}
      <div className="min-w-0">
        <h1 className="retro-banner__title">WhyLine Denver</h1>
        <p className="retro-banner__tagline">Ask anything about Denver transit</p>
      </div>
    </header>
  );
}
