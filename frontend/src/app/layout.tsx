import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Analytics } from "@vercel/analytics/next";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WhyLine Denver | RTD Reliability Analytics",
  description:
    "WhyLine Denver — Ask anything about Denver transit. Analyze RTD bus reliability, delays, safety, and equity gaps using natural language powered by DuckDB and BigQuery.",
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
      "Ask questions about Denver transit in plain English. Powered by DuckDB and BigQuery.",
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
    other: [{ rel: "mask-icon", url: "/assets/pinned-tab.svg", color: "#d4a574" }],
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
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body className="bg-background text-text antialiased">
        <Providers>{children}</Providers>
        <Analytics />
      </body>
    </html>
  );
}
