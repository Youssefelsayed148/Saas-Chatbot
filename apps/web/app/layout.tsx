import type { Metadata } from "next";
import "./globals.css";
import PageTitle from "@/lib/page-title";
import { ThemeProvider } from "@/lib/theme";
import { SessionProvider } from "@/lib/session";
import { dashboardFont } from "./fonts";

export const metadata: Metadata = {
  description: "Standalone website chatbot application foundation",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={dashboardFont.variable}>
        <PageTitle />
        <SessionProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
