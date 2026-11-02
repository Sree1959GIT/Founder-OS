import animate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

// Design tokens ("Graphite & Signal") from docs/design/README.md, exposed as CSS variables in src/index.css.
const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: token("border"),
        "border-strong": token("border-strong"),
        input: token("border-strong"),
        ring: token("signal"),
        background: token("bg"),
        foreground: token("text"),
        panel: token("panel"),
        card: { DEFAULT: token("card"), foreground: token("text") },
        muted: { DEFAULT: token("card"), foreground: token("text-muted") },
        primary: { DEFAULT: token("signal"), foreground: token("bg") },
        secondary: { DEFAULT: token("card"), foreground: token("text") },
        accent: { DEFAULT: token("card-hover"), foreground: token("text") },
        destructive: { DEFAULT: token("danger"), foreground: token("text") },
        signal: { DEFAULT: token("signal"), soft: token("signal-soft") },
        info: token("info"),
        ok: token("ok"),
        danger: token("danger"),
        paper: token("paper"),
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        serif: ['"Source Serif 4 Variable"', '"Source Serif 4"', "Georgia", "serif"],
      },
      borderRadius: {
        sm: "6px",
        md: "8px", // controls
        lg: "10px",
        xl: "12px", // cards
        "2xl": "14px",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
