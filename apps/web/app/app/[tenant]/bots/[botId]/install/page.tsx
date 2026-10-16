"use client";

/**
 * Install page (P4-03, docs/10 Install tab): the verified script snippet for
 * THIS deployment + a test-on-a-sample-page helper. The locator is NOT a
 * secret (docs/05) — it only names the bot; sessions carry the authority.
 */

import { useSession } from "@/lib/session";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";

function originOf(): string {
  // The snippet must point at whichever host serves the dashboard (so local
  // Compose and production produce the right URL); default to same origin.
  if (typeof window === "undefined") return "";
  if (window.location.port === "3000" || window.location.port) {
    return window.location.origin;
  }
  return window.location.origin;
}

export default function InstallPage() {
  const { me, roleIn } = useSession();
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const role = roleIn(tenantId);

  const [bot, setBot] = useState<api.Bot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        try {
          setBot(await api.getBot(tenantId, botId));
          setLoadError(null);
        } catch (caught) {
          setLoadError(
            caught instanceof Error
              ? caught.message
              : "Could not load this bot.",
          );
        }
      })();
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId, botId]);

  if (!me?.is_platform_staff && roleIn(tenantId) !== "admin")
    return (
      <main>
        <h1>Install</h1>
        <Notice message="Administrator access required." />
      </main>
    );

  if (loadError) {
    return (
      <main>
        <Notice message={loadError} tone="error" />
        <Link href={`/app/${tenantId}/bots`}>Back to bots</Link>
      </main>
    );
  }
  if (!bot) {
    return (
      <main>
        <Loading label="Loading bot…" />
      </main>
    );
  }

  const locator = bot.widget_locator ?? "";
  const snippet = `<script\n  src="${originOf()}/widget/v1/loader.js"\n  data-locator="${locator}"\n></script>`;
  const sampleUrl = `/widget/sample?locator=${encodeURIComponent(locator)}&site=custom`;

  return (
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1>{bot.name} — install</h1>
      <p className="page-purpose">
        Copy your widget snippet and verify it on the sample website.
      </p>
      <p data-status={bot.status} data-testid="install-status">
        Status: <LabelBadge value={bot.status} />
      </p>
      {bot.status !== "active" && (
        <Notice
          message={
            bot.status === "paused"
              ? 'The bot is paused — visitors get a controlled "unavailable" message. Reactivate it on the Settings tab.'
              : "The bot is still a draft — activate it on the Settings tab before installing."
          }
          tone={bot.status === "paused" ? "info" : "error"}
        />
      )}

      <section aria-label="Embed snippet">
        <h2>1. Paste this one script tag before &lt;/body&gt; of your site</h2>
        <pre data-testid="install-snippet">{snippet}</pre>
        <button
          type="button"
          disabled={!locator}
          data-testid="copy-snippet"
          onClick={() => {
            void navigator.clipboard
              .writeText(snippet)
              .then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy snippet"}
        </button>
        <p className="muted">
          The locator is public — it only names your bot. Only the domains you
          allow (Settings → allowed domains) may embed the assistant; visitor
          sessions are short-lived and rate-limited.
        </p>
      </section>

      <section aria-label="Test on a sample page">
        <h2>2. Test on a sample page</h2>
        {bot.status === "active" && bot.widget_locator ? (
          <p>
            <Link href={sampleUrl}>
              Open a sample page with this bot embedded
            </Link>{" "}
            (<code>/widget/sample?locator={locator}</code>) — chat there and
            come back to conversations to see the thread.
          </p>
        ) : (
          <p className="muted">
            Activate the bot to use the sample-page helper.
          </p>
        )}
      </section>

      <section aria-label="What visitors get">
        <h2>3. What your visitors get</h2>
        <ul>
          <li>
            Your assistant answers only from the published knowledge, in its
            language (EN/AR, RTL supported).
          </li>
          <li>Citations link back to the original pages when available.</li>
          <li>
            When it cannot answer, the reply points to your support contact.
          </li>
        </ul>
      </section>
      {role && (
        <p className="muted" aria-hidden="true">
          Role: {role}
        </p>
      )}
    </main>
  );
}
