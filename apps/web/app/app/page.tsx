"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";

export default function OrgSelectorPage() {
  const { me, loading, error, refresh } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    // Authentication check happens after the provider loads /me.
    if (!loading && !me && !error) {
      router.replace("/login");
    }
  }, [loading, me, error, router]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      const tenant = await api.createTenant(name);
      await refresh();
      router.push(`/app/${tenant.id}/bots`);
    } catch (caught) {
      setCreateError(
        caught instanceof Error
          ? caught.message
          : "Could not create organization.",
      );
    } finally {
      setCreating(false);
      setName("");
    }
  }

  return (
    <main>
      <h1>Your organizations</h1>
      <p className="page-purpose">
        Choose a workspace to manage its bots and conversations.
      </p>
      {loading && <Loading label="Loading organizations…" />}
      {!loading && error && <Notice message={error} tone="error" />}
      {!loading && !error && me && me.memberships.length === 0 && (
        <Empty>
          You do not belong to an organization yet. Create your first one below.
        </Empty>
      )}
      {!loading && !error && me && me.memberships.length > 0 && (
        <ul className="org-list">
          {me.memberships.map((membership) => (
            <li key={membership.tenant_id}>
              <Link href={`/app/${membership.tenant_id}/bots`}>
                {membership.tenant_name}
              </Link>
              <span className="muted"> — your role: {membership.role}</span>
            </li>
          ))}
        </ul>
      )}
      <section aria-label="Create organization">
        <h2>Create organization</h2>
        <form onSubmit={onCreate}>
          <label>
            Name
            <input
              name="name"
              required
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <button type="submit" disabled={creating || name.trim().length === 0}>
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
        {createError && <Notice message={createError} tone="error" />}
      </section>
    </main>
  );
}
