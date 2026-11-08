/** First focusable element on a page: jumps past the navigation to `#main`. */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:px-4 focus:py-2.5 focus:rounded-full focus:bg-wl-navy focus:text-white focus:font-extrabold"
    >
      Skip to content
    </a>
  );
}
