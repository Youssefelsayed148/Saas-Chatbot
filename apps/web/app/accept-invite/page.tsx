"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, LinkButton, Loading, Notice } from "@/lib/ui";
import "@/app/auth-screen.css";

function AcceptForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { me, loading: sessionLoading, refresh } = useSession();
  const [joined, setJoined] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const next = `/accept-invite?token=${encodeURIComponent(token)}`;

  async function onAccept() {
    setError(null);
    setBusy(true);
    try {
      await api.acceptInvitation(token);
      const meAfter = await refresh(); // the dashboard must see the new membership immediately
      const latest = meAfter?.memberships[meAfter.memberships.length - 1];
      setJoined(latest ? latest.tenant_name : "the organization");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not accept this invitation.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <main className="auth-page">
        <h1>Accept invitation</h1>
        <p className="page-purpose">
          Join your team’s workspace with your invited email.
        </p>
        <Notice
          message="This link is missing its invitation token."
          tone="error"
          scope="item"
        />
        <p className="auth-footer">
          <LinkButton variant="primary" href="/login">
            Sign in
          </LinkButton>
        </p>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <h1>Accept invitation</h1>
      <p className="page-purpose">
        Join your team’s workspace with your invited email.
      </p>
      {sessionLoading && <Loading label="Checking your session…" />}
      {!sessionLoading && me && !joined && (
        <>
          <p>
            Signed in as{" "}
            <strong>
              <bdi dir="ltr">{me.email}</bdi>
            </strong>
            . Accepting joins this account using the invited address.
          </p>
          <Button type="button" onClick={onAccept} disabled={busy}>
            {busy ? "Joining…" : "Accept invitation"}
          </Button>
        </>
      )}
      {!sessionLoading && !me && !joined && (
        <>
          <p>
            Sign in to accept this invitation with the invited email address.
          </p>
          <p>
            <LinkButton
              variant="primary"
              href={`/login?next=${encodeURIComponent(next)}`}
            >
              Sign in
            </LinkButton>
          </p>
        </>
      )}
      {joined && (
        <p role="status">
          Welcome aboard! You joined {joined}.{" "}
          <LinkButton variant="primary" href="/app">
            Go to your dashboard
          </LinkButton>
        </p>
      )}
      {error && <Notice message={error} tone="error" scope="item" />}
    </main>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<main className="eyebrow">Loading…</main>}>
      <AcceptForm />
    </Suspense>
  );
}
