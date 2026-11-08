import type { MetadataRoute } from "next";
import { PAGES, SITE } from "@/lib/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.map((path) => ({ url: `${SITE}${path === "/" ? "" : path}`, changeFrequency: path === "/app" ? "daily" : "monthly" }));
}
