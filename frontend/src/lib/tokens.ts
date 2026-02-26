/**
 * Brand color tokens — mirrors branding.py's BRAND_* constants.
 * Use these in chart configs and components that can't use Tailwind classes.
 */
export const tokens = {
  primary: "#87a7b3",   // Dusty Sky Blue
  accent: "#d4a574",    // Vintage Gold
  success: "#a3b88c",   // Sage Green
  warning: "#e8b863",   // Soft Amber
  error: "#c77f6d",     // Terra Cotta
  background: "#232129",
  surface: "#322e38",
  surfaceDark: "#1a171d",
  border: "#433f4c",
  text: "#e8d5c4",
  muted: "#9a8e7e",
} as const;

/** Chart color sequence — same order as CHART_COLORS in branding.py */
export const chartColors = [
  tokens.primary,
  tokens.success,
  tokens.accent,
  tokens.warning,
  tokens.error,
] as const;

/** RGBA versions for deck.gl layers */
export const rgbaTokens = {
  error: [199, 127, 109] as [number, number, number],
  primary: [135, 167, 179] as [number, number, number],
  accent: [212, 165, 116] as [number, number, number],
  success: [163, 184, 140] as [number, number, number],
} as const;

export const stripeGradient =
  "linear-gradient(90deg, #87a7b3 0%, #d4a574 25%, #a3b88c 50%, #e8b863 75%, #c77f6d 100%)";
