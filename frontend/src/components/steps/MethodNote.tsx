import { GLOSSARY, STOP_VISITS_SINCE } from "@/lib/links";

/** For results with an on-time column: shares from before the method change aren't comparable with later ones. */
export function MethodNote({ className = "" }: { className?: string }) {
  if (!STOP_VISITS_SINCE) return null;
  return (
    <details className={`wl-faq rounded-2xl bg-wl-gold-tint px-4 ${className}`}>
      <summary className="flex items-center justify-between gap-3 min-h-[48px] text-[15px] font-extrabold">
        On-time shares drop on {STOP_VISITS_SINCE}. Don’t compare across that date.
        <span aria-hidden="true" className="wl-plus flex-none w-7 h-7 rounded-full bg-white flex items-center justify-center text-lg leading-none">+</span>
      </summary>
      <p className="mt-0 pb-4 text-[15px] text-wl-ink2">
        Arrival times before {STOP_VISITS_SINCE} are estimated from 15-minute samples (accuracy ±minutes); from{" "}
        {STOP_VISITS_SINCE}, from 30-second vehicle reports (usually within 30 s for buses; each visit records its own
        uncertainty). On-time shares fall about 14 points at the switch, mostly because arrivals more than a minute early
        no longer count as on time, so don&apos;t compare the two periods. Bus figures also run 8–10 points below
        RTD&apos;s own, mostly from how RTD counts at its timepoints.{" "}
        <a href={`${GLOSSARY}#changed-definitions-at-the-cutover`} className="text-wl-navy font-extrabold underline">
          How arrivals are timed
        </a>
      </p>
    </details>
  );
}
