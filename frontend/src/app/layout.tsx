import type { Metadata } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";

const nunito = Nunito({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800", "900"],
  variable: "--font-nunito",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WhyLine Denver | RTD Reliability Analytics",
  description:
    "WhyLine Denver — Ask anything about Denver transit. Analyze RTD bus reliability, delays, safety, and equity gaps using natural language powered by BigQuery.",
  keywords: [
    "WhyLine Denver", "Denver transit analytics", "RTD bus delays",
    "Denver public transportation", "transit reliability dashboard",
    "Denver bus equity analysis", "RTD real-time GTFS",
  ],
  openGraph: {
    type: "website",
    url: "https://www.whylinedenver.com/app/",
    title: "WhyLine Denver | RTD Reliability Analytics",
    description:
      "Ask questions about Denver transit in plain English. Powered by BigQuery.",
    images: [{ url: "https://www.whylinedenver.com/assets/og-image.png", width: 1200, height: 630 }],
    siteName: "WhyLine Denver",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "WhyLine Denver | RTD Reliability Analytics",
    description: "Ask questions about Denver transit in plain English.",
    images: ["https://www.whylinedenver.com/assets/og-image.png"],
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/assets/logo.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "512x512", type: "image/png" }],
    other: [{ rel: "mask-icon", url: "/assets/pinned-tab.svg", color: "#042F54" }],
  },
  other: {
    "geo.region": "US-CO",
    "geo.placename": "Denver",
    "geo.position": "39.7392;-104.9903",
    ICBM: "39.7392, -104.9903",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={nunito.variable}>
      <body className="bg-wl-canvas text-wl-navy font-rounded antialiased">
        <Providers>{children}</Providers>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
