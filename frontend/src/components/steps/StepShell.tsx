export type StepStatus = "done" | "current" | "upcoming";

interface Props {
  n: number;
  title: string;
  status: StepStatus;
  last?: boolean;
  /** Shown beside the title, e.g. a status pill */
  aside?: React.ReactNode;
  children: React.ReactNode;
}

/** One stop on the Ask → Check → Results route: a numbered stop, the line to the next, and a card. */
export function StepShell({ n, title, status, last, aside, children }: Props) {
  return (
    <li className="flex gap-3 sm:gap-5">
      <div aria-hidden="true" className="flex-none w-10 sm:w-12 flex flex-col items-center">
        <div
          key={status}
          className={`wl-stopnum w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center font-black text-lg sm:text-xl ${
            status === "done"
              ? "is-done bg-wl-teal text-white shadow-[0_4px_0_#08485C]"
              : status === "current"
                ? "bg-wl-red text-white shadow-[0_4px_0_#A80F12]"
                : "bg-white text-wl-ink2 border-4 border-wl-road"
          }`}
        >
          {status === "done" ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12.5l4.5 4.5L19 7.5" />
            </svg>
          ) : (
            n
          )}
        </div>
        {!last && (
          <div
            className={`flex-1 mt-2 -mb-1 ${status === "done" ? "w-1.5 rounded-full bg-wl-teal" : "border-l-4 border-dotted border-wl-road"}`}
          />
        )}
      </div>
      <section aria-labelledby={`wl-step-${n}`} className={`flex-1 min-w-0 ${last ? "" : "pb-8"}`}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-h-[40px] sm:min-h-[48px]">
          <h2 id={`wl-step-${n}`} className={`m-0 font-black text-[22px] sm:text-2xl tracking-[-0.01em] ${status === "upcoming" ? "text-wl-ink2" : "text-wl-navy"}`}>
            <span className="sr-only">Step {n}{status === "done" ? ", done" : ""}: </span>
            {title}
          </h2>
          {aside}
        </div>
        <div className="mt-3">{children}</div>
      </section>
    </li>
  );
}
