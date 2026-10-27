/**
 * Brand color tokens (the logo's palette, same as the `wl-*` Tailwind colors).
 * Use these in chart configs and components that can't use Tailwind classes.
 */
export const tokens = {
  navy: "#042F54",
  navyDeep: "#021F38",
  teal: "#0D657F",
  gold: "#F0B616",
  red: "#D9191C",
  ink2: "#4A5F73",
  rule: "#E3EAF1",
  canvas: "#F4F8FB",
  white: "#FFFFFF",
} as const;

/**
 * Categorical chart hues in fixed order, brand-adjacent steps that pass the
 * dataviz validator (lightness, chroma, CVD) on white. Gold is under 3:1, so
 * charts always ship a legend or a table view.
 */
export const chartColors = ["#0A7FA0", "#D99A00", "#D9191C", "#3557B8", "#7D8C1F"] as const;

/** Shared Recharts styling: recessive axes and grid, white tooltip. */
export const chartTheme = {
  grid: { stroke: tokens.rule, vertical: false },
  tick: { fill: tokens.ink2, fontSize: 12, fontWeight: 600 },
  tooltip: {
    contentStyle: {
      backgroundColor: tokens.white,
      border: "none",
      borderRadius: 14,
      boxShadow: "0 12px 32px -12px rgba(4,47,84,.35)",
      fontWeight: 700,
    },
    labelStyle: { color: tokens.navy, fontWeight: 900 },
    itemStyle: { color: tokens.ink2 },
  },
} as const;
