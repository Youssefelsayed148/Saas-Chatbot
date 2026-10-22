"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  Button,
  DataTable,
  Empty,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";

export default function OrgSelectorPage() {
  const {
    me,
    loading,
    error,
    refresh,
    staffOrganizations,
    staffOrganizationsError,
  } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [selfServeSignup, setSelfServeSignup] = useState(false);

  useEffect(() => {
    let mounted = true;
    void api
      .authConfig()
      .then((features) => {
        if (mounted) setSelfServeSignup(features.self_serve_signup);
      })
      .catch(() => {
        if (mounted) setSelfServeSignup(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

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
      router.push(`/app/${tenant.id}`);
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

  if (!loading && !error && me?.is_platform_staff) {
    return (
      <main>
        <PageHeader
          title="All organizations"
          purpose="Open a client workspace or create an organization."
          actions={
            <>
              <Link href="/platform#create-organization">
                Create organization
              </Link>
              <Link href="/platform">Platform admin</Link>
            </>
          }
        />
        {staffOrganizationsError && (
          <Notice
            message={staffOrganizationsError}
            tone="error"
            onRetry={() => void refresh()}
          />
        )}
        {!staffOrganizations && !staffOrganizationsError && (
          <Loading label="Loading organizations…" />
        )}
        {staffOrganizations?.length === 0 && (
          <Empty>
            No organizations yet. Create your first organization to get started.
          </Empty>
        )}
        {!!staffOrganizations?.length && (
          <DataTable
            caption="All organizations"
            rows={staffOrganizations}
            rowKey={(org) => org.id}
            columns={[
              { key: "name", header: "Name", cell: (org) => org.name },
              { key: "plan", header: "Plan", cell: (org) => org.plan_label },
              {
                key: "status",
                header: "Status",
                cell: (org) => <StatusBadge value={org.status} />,
              },
              {
                key: "bots",
                header: "Bots",
                className: "num",
                cell: (org) => org.bots,
              },
              {
                key: "activity",
                header: "Last activity",
                cell: (org) =>
                  org.last_activity
                    ? new Date(org.last_activity).toLocaleString()
                    : "No activity yet",
              },
              {
                key: "workspace",
                header: "Workspace",
                cell: (org) => (
                  <Link
                    href={
                      org.status === "archived"
                        ? `/platform/clients/${org.id}`
                        : `/app/${org.id}`
                    }
                    aria-label={`Open ${org.name}`}
                  >
                    Open
                  </Link>
                ),
              },
            ]}
          />
        )}
      </main>
    );
  }

  return (
    <main>
      <PageHeader
        title="Your organizations"
        purpose="Choose a workspace to manage its bots and conversations."
      />
      {loading && <Loading label="Loading organizations…" />}
      {!loading && error && <Notice message={error} tone="error" />}
      {!loading &&
        !error &&
        me &&
        me.memberships.length === 0 &&
        selfServeSignup && (
          <Empty>
            You do not belong to an organization yet. Create your first one
            below.
          </Empty>
        )}
      {!loading && !error && me && me.memberships.length > 0 && (
        <ul className="org-list">
          {me.memberships.map((membership) => (
            <li key={membership.tenant_id}>
              <Link href={`/app/${membership.tenant_id}`}>
                {membership.tenant_name}
              </Link>
              <span className="muted"> — your role: {membership.role}</span>
            </li>
          ))}
        </ul>
      )}
      {!loading && !error && me && selfServeSignup && (
        <section aria-label="Create organization">
          <h2>Create organization</h2>
          <form onSubmit={onCreate}>
            <Field label="Name">
              {(control) => (
                <input
                  {...control}
                  name="name"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              )}
            </Field>
            <Button
              type="submit"
              disabled={creating || name.trim().length === 0}
            >
              {creating ? "Creating…" : "Create"}
            </Button>
          </form>
          {createError && <Notice message={createError} tone="error" />}
        </section>
      )}
      {!loading &&
        !error &&
        me &&
        me.memberships.length === 0 &&
        !selfServeSignup && (
          <Empty>
            Your account needs an invitation to join an organization.
          </Empty>
        )}
    </main>
  );
}
