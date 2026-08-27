/** @type {import('tailwindcss').Config} */
import type { Config } from "tailwindcss";

// Obsidian Orbit design tokens are surfaced through CSS custom properties
// (styles/tokens.css) AND mirrored here as Tailwind theme keys so utility
// classes like `bg-obsidian` / `text-data-blue` read ergonomically.
// Source of truth for the *values* is tokens.css; this maps tokens to names.
const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        obsidian: {
          DEFAULT: "var(--obsidian-bg)",
          surface: "var(--color-surface)",
          "surface-dim": "var(--color-surface-dim)",
          "surface-bright": "var(--color-surface-bright)",
          "surface-lowest": "var(--color-surface-lowest)",
          "surface-low": "var(--color-surface-low)",
          "surface-high": "var(--color-surface-high)",
          "surface-highest": "var(--color-surface-highest)",
          "on-surface": "var(--color-on-surface)",
          "on-surface-variant": "var(--color-on-surface-variant)",
          outline: "var(--color-outline)",
          "outline-variant": "var(--color-outline-variant)",
        },
        "data-blue": {
          DEFAULT: "var(--data-blue)",
          dim: "var(--data-blue-dim)",
          container: "var(--data-blue-container)",
          "on-container": "var(--data-blue-on-container)",
        },
        "safety-amber": {
          DEFAULT: "var(--safety-amber)",
          container: "var(--safety-amber-container)",
          "on-container": "var(--safety-amber-on-container)",
        },
        "neural-violet": {
          DEFAULT: "var(--neural-violet)",
          container: "var(--neural-violet-container)",
          "on-container": "var(--neural-violet-on-container)",
        },
        neutral: {
          white: "#ffffff",
          "grey-80": "var(--text-body)",
          "grey-60": "var(--text-muted)",
          "grey-40": "var(--text-faint)",
        },
      },
      fontFamily: {
        display: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "display-xl": ["clamp(2.75rem, 6vw, 4.5rem)", { lineHeight: "0.98", letterSpacing: "-0.02em" }],
        "headline-lg": ["clamp(1.75rem, 3.4vw, 2.5rem)", { lineHeight: "1.1", letterSpacing: "-0.01em" }],
        "headline-md": ["1.5rem", { lineHeight: "1.25" }],
        "headline-sm": ["1.25rem", { lineHeight: "1.3" }],
        "body-lg": ["1.125rem", { lineHeight: "1.6" }],
        "body-md": ["1rem", { lineHeight: "1.5" }],
        "body-sm": ["0.875rem", { lineHeight: "1.5" }],
        "data-label": ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.08em" }],
      },
      borderRadius: {
        sm: "0.125rem",
        md: "0.25rem",
        lg: "0.375rem",
        xl: "0.5rem",
        "2xl": "0.75rem",
        full: "9999px",
      },
      spacing: {
        "stack-sm": "8px",
        "stack-md": "24px",
        "stack-lg": "64px",
        gutter: "24px",
        "margin-safe": "32px",
      },
      maxWidth: {
        container: "1440px",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "pulse-scan": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "0.8" },
        },
        "spin-slow": {
          to: { transform: "rotate(360deg)" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-scan": "pulse-scan 4s ease-in-out infinite",
        "spin-slow": "spin-slow 18s linear infinite",
        "fade-in-up": "fade-in-up 0.7s cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};

export default config;