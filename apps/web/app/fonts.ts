import localFont from "next/font/local";

/**
 * Dashboard font (D.2): one self-hosted, Arabic-capable variable font.
 * Applied to the dashboard through the --font-dashboard CSS variable on <body>;
 * the widget frame keeps its own --font stack until Batch C is merged.
 *
 * Cairo (variable), Arabic + Latin, weight 200-1000. See app/fonts/README.md
 * for the source and the OFL licence beside the file. No external font
 * request is made.
 */
export const dashboardFont = localFont({
  src: "./fonts/dashboard-font.woff2",
  variable: "--font-dashboard",
  weight: "200 1000",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  fallback: [
    "ui-sans-serif",
    "system-ui",
    "-apple-system",
    "Segoe UI",
    "sans-serif",
  ],
});
