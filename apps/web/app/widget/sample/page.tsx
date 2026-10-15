"use client";

/**
 * Sample page (P4-03): "test on a sample page" — a stand-in customer page
 * served by this deployment that embeds the REAL loader snippet. This lets
 * the operator verify the install before pasting it on their own site, and
 * doubles as the static test site for the widget E2E (docs/09, docs/10).
 *
 * Note: on this local/loopback deployment only same-origin embeds perform the
 * full Chrome Local-Network-Access dance; real customer sites embed
 * cross-origin from public hosts, where classic <script src> needs no CORS
 * (docs: packages/widget/README.md).
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

function SamplePage() {
  const params = useSearchParams();
  const locator = params.get("locator") ?? "";
  const site = params.get("site") ?? "store-a";

  return (
    <main className="sample-page">
      <p className="eyebrow">WIDGET PREVIEW · SAMPLE WEBSITE</p>
      <h1>
        {site === "store-b" ? "Store B (sample site)" : "Store A (sample site)"}
      </h1>
      <p>
        This page stands in for a customer website. It embeds the widget exactly
        the way the Install tab shows it — one script tag with the bot locator:
      </p>
      <pre data-testid="sample-snippet">
        {`
<script
  src="/widget/v1/loader.js"
  data-locator="${locator}"
></script>`}
      </pre>
      <p className="muted sample-tip">
        Use the chat bubble to verify the assistant answers from this bot&apos;s
        published knowledge.
      </p>
      {locator ? (
        <ScriptEmbed locator={locator} />
      ) : (
        <p data-testid="sample-missing-locator" role="alert">
          Missing locator — open this page as /widget/sample?locator=&lt;bot
          locator&gt;
        </p>
      )}
    </main>
  );
}

function ScriptEmbed({ locator }: { locator: string }) {
  const anchor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Append a REAL script element (innerHTML scripts never execute): this is
    // exactly the element the customer's script tag produces, with
    // data-locator on it (the loader reads data-locator or falls back to the
    // last script with "loader" in its src).
    const element = document.createElement("script");
    element.src = "/widget/v1/loader.js";
    element.setAttribute(
      "data-locator",
      locator.replace(/[^A-Za-z0-9_-]/g, ""),
    );
    anchor.current?.appendChild(element);
  }, [locator]);
  return <div ref={anchor} />;
}

export default function WidgetSamplePage() {
  return (
    <Suspense fallback={null}>
      <SamplePage />
    </Suspense>
  );
}
