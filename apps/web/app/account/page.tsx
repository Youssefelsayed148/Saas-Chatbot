"use client";

/**
 * /account (S4): one account page for every signed-in user. Reachable from
 * the client workspace and the platform admin via the header Account link.
 * The shell renders in the caller's own mode; the API itself is the guard
 * (401 for anonymous callers, no role logic in the endpoint).
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AccountForm } from "@/lib/account";
import { AppShell } from "@/lib/app-header";
import { useSession } from "@/lib/session";
import { Card, PageHeader } from "@/lib/ui";
import "@/app/auth-screen.css";

export default function AccountPage() {
  const { me, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) router.replace("/login?next=/account");
  }, [loading, me, router]);

  if (loading || !me) return null;

  return (
    <AppShell platform={me.is_platform_staff}>
      <main className="account-page">
        <PageHeader
          title="Account"
          purpose="Your signed-in account and password."
        />
        <Card className="account-identity">
          <p data-testid="account-email">Signed in as {me.email}</p>
        </Card>
        <AccountForm />
      </main>
    </AppShell>
  );
}
