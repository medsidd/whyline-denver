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
        primary: "#87a7b3",
        accent: "#d4a574",
        success: "#a3b88c",
        warning: "#e8b863",
        error: "#c77f6d",
        background: "#232129",
        surface: "#322e38",
        border: "#433f4c",
        text: "#e8d5c4",
        muted: "#9a8e7e",
        "surface-dark": "#1a171d",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        heading: ["var(--font-space-grotesk)", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Courier New", "monospace"],
      },
      backgroundImage: {
        stripe:
          "linear-gradient(90deg, #87a7b3 0%, #d4a574 25%, #a3b88c 50%, #e8b863 75%, #c77f6d 100%)",
        "brand-gradient":
          "linear-gradient(135deg, #87a7b3 0%, #d4a574 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
