import { readableTimestamp } from "@/lib/format";

/**
 * For SQL that reads the live views. With a result, `loadedAt` is when the newest vehicle report
 * was made ("YYYY-MM-DD HH:MM UTC"); reports load every 15 minutes.
 */
export function LiveNote({ className = "", loadedAt }: { className?: string; loadedAt?: string | null }) {
  return (
    <p role="note" className={`m-0 flex items-start gap-2 px-4 py-2.5 rounded-2xl bg-wl-teal-tint text-[14px] font-bold text-wl-navy ${className}`}>
      <span aria-hidden="true" className="flex-none mt-1.5 w-2.5 h-2.5 rounded-full bg-wl-teal animate-pulse motion-reduce:animate-none" />
      <span>
        Live data{loadedAt ? `, newest vehicle report ${readableTimestamp(loadedAt)}` : ""}. It trails real time by 15–30
        minutes, because vehicle reports load every 15 minutes.
      </span>
    </p>
  );
}
