import type { Metadata } from "next";

export const SITE = "https://www.whylinedenver.com";

/**
 * Title, description, canonical URL and link previews for one page. Next.js replaces a parent's
 * openGraph object rather than merging it, so each page sets the whole thing here.
 */
export function pageMetadata({ title, description, path }: { title: string; description: string; path: string }): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      url: path,
      title,
      description,
      images: [{ url: "/assets/og-image.png", width: 1200, height: 630 }],
      siteName: "WhyLine Denver",
      locale: "en_US",
    },
    twitter: { card: "summary_large_image", title, description, images: ["/assets/og-image.png"] },
  };
}

/** Public pages, for the sitemap. */
export const PAGES = ["/", "/app", "/privacy", "/terms", "/attribution"] as const;
