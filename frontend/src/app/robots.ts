import type { MetadataRoute } from "next";
import { SITE } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  // /api/* is the data proxy: query results, not pages.
  return { rules: { userAgent: "*", allow: "/", disallow: "/api/" }, sitemap: `${SITE}/sitemap.xml` };
}
