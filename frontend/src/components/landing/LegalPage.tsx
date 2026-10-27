import Image from "next/image";
import Link from "next/link";
import { SiteFooter } from "./SiteFooter";

/** Shell for the privacy, terms and attribution pages, in the landing design language. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="wl min-h-screen flex flex-col bg-wl-canvas text-wl-navy font-rounded text-[17px] leading-[1.6] font-medium">
      <header className="wl-nav sticky top-0 z-30 border-b border-wl-navy/[0.08]">
        <nav aria-label="Main" className="max-w-[1200px] mx-auto px-[clamp(16px,4vw,48px)] h-16 flex items-center gap-3 sm:gap-6">
          <Link href="/" className="flex items-center gap-2 sm:gap-2.5 min-h-[44px] text-wl-navy">
            <Image src="/assets/logo-512.png" alt="" width={36} height={36} priority />
            <span className="font-black text-[17px] sm:text-xl tracking-[-0.01em] whitespace-nowrap">WhyLine Denver</span>
          </Link>
          <Link
            href="/app"
            className="wl-btn wl-btn-navy ml-auto inline-flex items-center h-11 px-4 sm:px-[22px] rounded-full bg-wl-navy text-white font-extrabold text-sm sm:text-[15px] whitespace-nowrap"
          >
            Open dashboard
          </Link>
        </nav>
      </header>
      <main className="flex-1 w-full max-w-[1200px] mx-auto px-[clamp(16px,4vw,48px)] py-16">
        <article className="wl-legal wl-shadow bg-white rounded-[32px] p-[clamp(24px,5vw,64px)] max-w-[860px]">
          <h1 className="m-0 font-black text-[clamp(36px,5vw,56px)] leading-[1.05] tracking-[-0.035em] text-wl-navy">{title}</h1>
          <p className="mt-3 text-sm font-bold text-wl-ink2">Last updated {updated}</p>
          {children}
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
