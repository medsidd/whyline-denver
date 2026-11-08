import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/landing/LegalPage";

// Next.js adds noindex to not-found pages itself.
export const metadata: Metadata = { title: "Page not found | WhyLine Denver" };

export default function NotFound() {
  return (
    <LegalPage title="This page isn’t on the map">
      <p>The link may be old, or the address may have a typo. Try one of these instead.</p>
      {/* ! beats the .wl-legal p and a rules (margin, teal, weight 800) */}
      <p className="flex flex-wrap gap-3 !mt-6">
        <Link href="/" className="wl-btn wl-btn-navy inline-flex items-center h-12 px-6 rounded-full bg-wl-navy !text-white !font-black !no-underline">
          Back to home
        </Link>
        <Link href="/app" className="wl-btn inline-flex items-center h-12 px-6 rounded-full border-2 border-wl-navy bg-white !text-wl-navy !font-black !no-underline">
          Open dashboard
        </Link>
      </p>
    </LegalPage>
  );
}
