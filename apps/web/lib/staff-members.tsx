"use client";

import { useEffect, useState } from "react";
import * as api from "./api";
import { ConfirmAction, Notice } from "./ui";

export function RoleSelect({
  value,
  onChange,
}: {
  value: api.ClientRole;
  onChange: (role: api.ClientRole) => void;
}) {
  return (
    <label>
      Role
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as api.ClientRole)}
      >
        {(["admin", "editor", "viewer"] as const).map((role) => (
          <option key={role}>{role}</option>
        ))}
      </select>
    </label>
  );
}

export function OrganizationSelect({
  value,
  onChange,
  optional = false,
  emptyLabel,
  activeOnly = true,
}: {
  value: string;
  onChange: (id: string) => void;
  optional?: boolean;
  emptyLabel?: string;
  activeOnly?: boolean;
}) {
  const [organizations, setOrganizations] = useState<api.PlatformTenantRow[]>(
    [],
  );
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void (async () => {
      const all: api.PlatformTenantRow[] = [];
      for (let offset = 0; ; offset += 100) {
        const result = await api.platformTenants(
          `${activeOnly ? "status=active&" : ""}limit=100&offset=${offset}`,
        );
        all.push(...result.tenants);
        if (all.length >= result.total || result.tenants.length === 0) break;
      }
      if (alive) setOrganizations(all);
    })().catch(() => {
      if (alive) setError("Could not load organizations.");
    });
    return () => {
      alive = false;
    };
  }, [activeOnly]);
  return (
    <>
      <label>
        Organization
        <select
          required={!optional}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {emptyLabel ??
              (optional ? "No organization" : "Choose organization")}
          </option>
          {organizations.map((org) => (
            <option key={org.id} value={org.id}>
              {org.name}
            </option>
          ))}
        </select>
      </label>
      {error && <Notice tone="error" message={error} />}
    </>
  );
}

export function PasswordPanel({
  password,
  onDismiss,
}: {
  password: string;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  return (
    <section aria-label="One-time password">
      <h2>Password — shown once</h2>
      <code data-testid="issued-password">{password}</code>
      <p>Share this with the user; they should change it after first login.</p>
      <button
        type="button"
        onClick={() => {
          void (async () => {
            try {
              await navigator.clipboard.writeText(password);
              setCopied(true);
            } catch {
              setError("Copy failed. Select and copy the password manually.");
            }
          })();
        }}
      >
        Copy password
      </button>
      {copied && <span role="status">Copied.</span>}
      {error && <p role="alert">{error}</p>}
      <button type="button" onClick={onDismiss}>
        Dismiss password
      </button>
    </section>
  );
}

export function MembershipControls({
  user,
  refresh,
}: {
  user: api.StaffUser;
  refresh: () => Promise<void>;
}) {
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState<api.ClientRole>("viewer");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Membership update failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Memberships">
      <h2>Memberships</h2>
      {error && <Notice tone="error" message={error} />}
      {user.memberships.map((m) => (
        <div key={m.organization_id}>
          <p>
            {m.organization_name} · {m.status}
          </p>
          {m.status === "active" && (
            <>
              <RoleSelect
                value={m.role}
                onChange={(role) => {
                  void perform(() =>
                    api.platformUserRole(user.id, m.organization_id, role),
                  );
                }}
              />
              <ConfirmAction
                title="Remove membership"
                description={`Remove ${user.email} from ${m.organization_name}?`}
                disabled={busy}
                onConfirm={() => {
                  void perform(() =>
                    api.platformRemoveUser(user.id, m.organization_id),
                  );
                }}
              >
                Remove membership
              </ConfirmAction>
            </>
          )}
        </div>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void perform(() =>
            api.platformAssignUser(user.id, organization, role),
          );
        }}
      >
        <OrganizationSelect value={organization} onChange={setOrganization} />
        <RoleSelect value={role} onChange={setRole} />
        <button disabled={busy}>Add membership</button>
      </form>
    </section>
  );
}

export function OrganizationMembers({
  organization,
  refresh,
}: {
  organization: string;
  refresh: () => Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<api.ClientRole>("viewer");
  const [users, setUsers] = useState<api.StaffUser[]>([]);
  const [selected, setSelected] = useState("");
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update members.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Manage organization members">
      {error && <Notice tone="error" message={error} />}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void perform(async () => {
            const result = await api.platformUsers(
              new URLSearchParams({ q: email }).toString(),
            );
            setUsers(result.users);
            setSelected("");
          });
        }}
      >
        <label>
          Search email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <button disabled={busy}>Search users</button>
      </form>
      <label>
        Existing user
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Choose user</option>
          {users.map((u) => (
            <option value={u.id} key={u.id}>
              {u.email}
            </option>
          ))}
        </select>
      </label>
      <RoleSelect value={role} onChange={setRole} />
      <button
        disabled={busy || !selected}
        onClick={() => {
          void perform(() =>
            api.platformAssignUser(selected, organization, role),
          );
        }}
      >
        Add existing user
      </button>
      <button
        disabled={busy || !email}
        onClick={() => {
          void perform(async () => {
            const result = await api.createInvitation(
              organization,
              email,
              role,
            );
            setLink(result.link_path ?? "");
          });
        }}
      >
        Invite existing user
      </button>
      {link && (
        <p>
          Share this invitation: <code>{link}</code>
          <button onClick={() => setLink("")}>Dismiss invitation</button>
        </p>
      )}
    </section>
  );
}
