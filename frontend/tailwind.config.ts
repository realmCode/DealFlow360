import type { Config } from "tailwindcss";

/** Every colour resolves to a token in design-system/tokens.css. */
const t = (name: string) => `var(--${name})`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: t("ink-950"), 900: t("ink-900"), 800: t("ink-800"), 700: t("ink-700"),
          600: t("ink-600"), 500: t("ink-500"), 400: t("ink-400"), 300: t("ink-300"),
          200: t("ink-200"), 150: t("ink-150"), 100: t("ink-100"), 50: t("ink-50"),
        },
        accent: {
          900: t("accent-900"), 800: t("accent-800"), 700: t("accent-700"),
          600: t("accent-600"), 500: t("accent-500"), 400: t("accent-400"),
          300: t("accent-300"), 200: t("accent-200"), 100: t("accent-100"),
          50: t("accent-50"),
        },
        gov: {
          700: t("gov-700"), 600: t("gov-600"), 500: t("gov-500"),
          300: t("gov-300"), 100: t("gov-100"), 50: t("gov-50"),
        },
        chrome: {
          DEFAULT: t("chrome"), hi: t("chrome-hi"), line: t("chrome-line"),
          text: t("chrome-text"), dim: t("chrome-text-dim"),
        },
        canvas: t("canvas"),
        surface: { DEFAULT: t("surface"), sunken: t("surface-sunken") },
        line: { DEFAULT: t("line"), soft: t("line-soft"), strong: t("line-strong") },
        rail: { DEFAULT: t("rail"), hover: t("rail-hover"), active: t("rail-active") },
        content: {
          DEFAULT: t("text"), secondary: t("text-secondary"),
          muted: t("text-muted"), faint: t("text-faint"), invert: t("text-invert"),
        },
        value: { up: t("value-up"), down: t("value-down"), flat: t("value-flat") },
        margin: { healthy: t("margin-healthy"), thin: t("margin-thin"), breach: t("margin-breach") },
      },
      fontFamily: {
        ui: [t("font-ui")],
        body: [t("font-body")],
        num: [t("font-num")],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px", letterSpacing: "0.06em" }],
        xs: ["11px", { lineHeight: "16px" }],
        sm: ["12px", { lineHeight: "18px" }],
        base: ["13px", { lineHeight: "20px" }],
        md: ["14px", { lineHeight: "21px" }],
        lg: ["16px", { lineHeight: "24px" }],
        xl: ["19px", { lineHeight: "26px", letterSpacing: "-0.01em" }],
        "2xl": ["23px", { lineHeight: "30px", letterSpacing: "-0.015em" }],
        "3xl": ["29px", { lineHeight: "36px", letterSpacing: "-0.02em" }],
        "4xl": ["36px", { lineHeight: "42px", letterSpacing: "-0.025em" }],
        "5xl": ["46px", { lineHeight: "52px", letterSpacing: "-0.03em" }],
      },
      borderRadius: {
        xs: t("r-xs"), sm: t("r-sm"), DEFAULT: t("r-md"), md: t("r-md"),
        lg: t("r-lg"), xl: t("r-xl"), pill: t("r-pill"),
      },
      boxShadow: {
        xs: t("shadow-xs"),
        sm: t("shadow-sm"),
        pop: t("shadow-pop"),
        overlay: t("shadow-overlay"),
        ring: t("ring"),
      },
      spacing: {
        topbar: t("topbar-h"),
        sidebar: t("sidebar-w"),
        row: t("row-h"),
      },
      transitionTimingFunction: { smooth: t("ease") },
      transitionDuration: { fast: "140ms", base: "200ms", slow: "280ms" },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "slide-in-left": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "rail-pulse": {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms cubic-bezier(0.32,0.72,0,1)",
        "slide-up": "slide-up 220ms cubic-bezier(0.32,0.72,0,1)",
        "slide-in-right": "slide-in-right 280ms cubic-bezier(0.32,0.72,0,1)",
        "slide-in-left": "slide-in-left 240ms cubic-bezier(0.32,0.72,0,1)",
        shimmer: "shimmer 1400ms infinite",
        "rail-pulse": "rail-pulse 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
