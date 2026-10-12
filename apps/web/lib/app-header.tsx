"use client";

/** Shared shell for /app pages: header with org switcher and sign-out. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePathname } from "next/navigation";

import * as api from "./api";
import { useSession } from "./session";

export function AppHeader({ tenantId }: { tenantId?: string }) {
  const { me, refresh } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  async function signOut() {
    await api.logout();
    await refresh();
    router.push("/login");
  }

  async function switchOrg(tenantIdValue: string) {
    router.push(`/app/${tenantIdValue}/bots`);
  }

  return (
    <header className="app-header">
      <p className="eyebrow">
        <Link href="/app">Dashboard</Link>
      </p>
      {me && (
        <nav aria-label="Organization">
          <label>
            Organization
            <select
              value={tenantId ?? ""}
              onChange={(event) => switchOrg(event.target.value)}
              aria-label="Organization selector"
            >
              {!tenantId && <option value="">Select…</option>}
              {me.memberships.map((membership) => (
                <option key={membership.tenant_id} value={membership.tenant_id}>
                  {membership.tenant_name}
                </option>
              ))}
            </select>
          </label>
          {tenantId && (
            <>
              <Link
                href={`/app/${tenantId}/bots`}
                aria-current={pathname?.includes("/bots") ? "page" : undefined}
              >
                Bots
              </Link>
              <Link
                href={`/app/${tenantId}/settings/members`}
                aria-current={
                  pathname?.endsWith("/members") ? "page" : undefined
                }
              >
                Team
              </Link>
            </>
          )}
          <span className="muted">{me.email}</span>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </nav>
      )}
    </header>
  );
}
