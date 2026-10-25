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
import {
  Button,
  Card,
  LinkButton,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";

import "@/app/install-screen.css";

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
    if (!me?.is_platform_staff) return;
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
  }, [tenantId, botId, me?.is_platform_staff]);

  if (!me?.is_platform_staff) return null;

  if (loadError) {
    return (
      <main className="install-page">
        <Notice message={loadError} tone="error" />
        <LinkButton
          variant="ghost"
          className="install-back"
          href={`/app/${tenantId}/bots`}
        >
          Back to bots
        </LinkButton>
      </main>
    );
  }
  if (!bot) {
    return (
      <main className="install-page">
        <Loading label="Loading bot…" />
      </main>
    );
  }

  const locator = bot.widget_locator ?? "";
  const snippet = `<script\n  src="${originOf()}/widget/v1/loader.js"\n  data-locator="${locator}"\n></script>`;
  const sampleUrl = `/widget/sample?locator=${encodeURIComponent(locator)}&site=custom`;

  return (
    <main className="install-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title={
          <>
            <bdi dir="auto">{bot.name}</bdi> — install
          </>
        }
        purpose="Copy your widget snippet and verify it on the sample website."
      />
      <p
        data-status={bot.status}
        data-testid="install-status"
        className="install-status"
      >
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

      <Card
        title="1. Paste this one script tag before </body> of your site"
        aria-label="Embed snippet"
      >
        <pre
          data-testid="install-snippet"
          dir="ltr"
          className="install-snippet"
        >
          {snippet}
        </pre>
        <div className="install-actions">
          <Button
            disabled={!locator}
            data-testid="copy-snippet"
            onClick={() => {
              void navigator.clipboard
                .writeText(snippet)
                .then(() => setCopied(true));
            }}
          >
            {copied ? "Copied" : "Copy snippet"}
          </Button>
        </div>
        <p className="install-note">
          The locator is public — it only names your bot. Only the domains you
          allow (Settings → allowed domains) may embed the assistant; visitor
          sessions are short-lived and rate-limited.
        </p>
      </Card>

      <Card title="2. Test on a sample page" aria-label="Test on a sample page">
        {bot.status === "active" && bot.widget_locator ? (
          <p>
            <Link href={sampleUrl}>
              Open a sample page with this bot embedded
            </Link>{" "}
            (<code dir="ltr">/widget/sample?locator={locator}</code>) — chat
            there and come back to conversations to see the thread.
          </p>
        ) : (
          <p className="muted">
            Activate the bot to use the sample-page helper.
          </p>
        )}
      </Card>

      <Card title="3. What your visitors get" aria-label="What visitors get">
        <ul className="install-points">
          <li>
            Your assistant answers only from the published knowledge, in its
            language (EN/AR, RTL supported).
          </li>
          <li>Citations link back to the original pages when available.</li>
          <li>
            When it cannot answer, the reply points to your support contact.
          </li>
        </ul>
      </Card>
      {role && (
        <p className="muted" aria-hidden="true">
          Role: {role}
        </p>
      )}
    </main>
  );
}
