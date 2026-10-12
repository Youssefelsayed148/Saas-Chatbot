"use client";

/** Small presentational helpers shared by the dashboard pages (loading/empty/error states). */

import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="eyebrow">
      {label}
    </p>
  );
}

export function Notice({
  message,
  tone = "info",
}: {
  message: string;
  tone?: "info" | "error";
}) {
  return (
    <p role={tone === "error" ? "alert" : "status"} data-tone={tone}>
      {message}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted">{children}</p>;
}
