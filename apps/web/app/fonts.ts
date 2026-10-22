import localFont from "next/font/local";

/**
 * Dashboard font (D.2): one self-hosted, Arabic-capable variable font.
 * Applied to the dashboard through the --font-dashboard CSS variable on <body>;
 * the widget frame keeps its own --font stack until Batch C is merged.
 *
 * The file below is a 0-byte PLACEHOLDER so the build stays green. Browsers
 * reject it and fall back to the system font stack (one console warning:
 * "Failed to decode downloaded font"). Replace it with the real file, same
 * name and path, see app/fonts/README.md. No external font request is made.
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
