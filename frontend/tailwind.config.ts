import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // WhyLine design language (the logo's colors)
        wl: {
          navy: "#042F54",
          "navy-deep": "#021F38",
          gold: "#F0B616",
          red: "#D9191C",
          teal: "#0D657F",
          canvas: "#F4F8FB",
          ink2: "#4A5F73",
          rule: "#E3EAF1",
          road: "#C9D6E3",
          "teal-tint": "#DFF0F4",
          "gold-tint": "#FFF0C7",
          "red-tint": "#FDE4E3",
          "navy-tint": "#E5EDF5",
        },
      },
      fontFamily: {
        rounded: ["var(--font-nunito)", "ui-rounded", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
