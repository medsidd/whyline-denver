"use client";

import { TOPICS } from "@/lib/topics";
import { useDashboardStore } from "@/store/dashboardStore";

/** What you can ask about, with an example per topic that fills the question box (nothing runs). */
export function TopicsPanel() {
  const { setQuestion, resetForNewQuestion } = useDashboardStore();

  return (
    <details className="wl-faq mt-5 rounded-[22px] bg-white/70 border-2 border-wl-navy/[0.06] px-4">
      <summary className="flex items-center justify-between gap-3 min-h-[48px] text-sm font-extrabold text-wl-ink2">
        What can I ask about?
        <span aria-hidden="true" className="wl-plus flex-none w-7 h-7 rounded-full bg-wl-navy-tint flex items-center justify-center text-lg leading-none text-wl-navy">
          +
        </span>
      </summary>
      <ul className="m-0 mb-4 p-0 list-none grid sm:grid-cols-2 gap-x-6 gap-y-4">
        {TOPICS.map((t) => (
          <li key={t.name} className="min-w-0">
            <p className="m-0 flex items-center gap-2 font-black text-[15px] text-wl-navy">
              <span aria-hidden="true" className={`flex-none w-5 h-2 rounded ${t.line}`} />
              {t.name}
            </p>
            <p className="mt-1 mb-1.5 text-sm font-semibold text-wl-ink2">{t.body}</p>
            <button
              type="button"
              onClick={() => {
                // A new question: clear the loaded SQL and results, as the landing page's ?q= link does
                resetForNewQuestion();
                setQuestion(t.example);
                const box = document.getElementById("wl-question");
                // Focusing on a touch screen would open the keyboard over the page
                if (window.matchMedia("(pointer: fine)").matches) box?.focus();
                else box?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className={`text-left py-2 px-3 rounded-2xl rounded-bl-md ${t.tint} text-sm font-bold text-wl-navy hover:underline`}
            >
              “{t.example}”
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
