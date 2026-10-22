"use client";

import { useEffect, useState } from "react";
import * as api from "./api";
import { Button, Card, ConfirmAction, Field, Notice } from "./ui";
import "@/app/staff-screens.css";

export function RoleSelect({
  value,
  onChange,
}: {
  value: api.ClientRole;
  onChange: (role: api.ClientRole) => void;
}) {
  return (
    <Field label="Role">
      {(control) => (
        <select
          {...control}
          value={value}
          onChange={(e) => onChange(e.target.value as api.ClientRole)}
        >
          {(["admin", "editor", "viewer"] as const).map((role) => (
            <option key={role}>{role}</option>
          ))}
        </select>
      )}
    </Field>
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
      <Field label="Organization">
        {(control) => (
          <select
            {...control}
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
        )}
      </Field>
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
    <Card
      aria-label="One-time password"
      title="Password — shown once"
      className="password-panel"
    >
      <code data-testid="issued-password">{password}</code>
      <p>Share this with the user; they should change it after first login.</p>
      <div className="action-row">
        <Button
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
        </Button>
        {copied && <span role="status">Copied.</span>}
        <Button type="button" variant="quiet" onClick={onDismiss}>
          Dismiss password
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
    </Card>
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
    <section aria-label="Memberships" className="form-section">
      <header>
        <h2>Memberships</h2>
      </header>
      {error && <Notice tone="error" message={error} />}
      {user.memberships.map((m) => (
        <div key={m.organization_id} className="membership-row">
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
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          void perform(() =>
            api.platformAssignUser(user.id, organization, role),
          );
        }}
      >
        <OrganizationSelect value={organization} onChange={setOrganization} />
        <RoleSelect value={role} onChange={setRole} />
        <Button type="submit" disabled={busy}>
          Add membership
        </Button>
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
    <section aria-label="Manage organization members" className="form-section">
      <header>
        <h2>Add people</h2>
        <p>Find an existing user to add, or send them an invitation link.</p>
      </header>
      {error && <Notice tone="error" message={error} />}
      <form
        className="inline-form"
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
        <Field label="Search email">
          {(control) => (
            <input
              {...control}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" disabled={busy}>
          Search users
        </Button>
      </form>
      <div className="inline-form">
        <Field label="Existing user">
          {(control) => (
            <select
              {...control}
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Choose user</option>
              {users.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.email}
                </option>
              ))}
            </select>
          )}
        </Field>
        <RoleSelect value={role} onChange={setRole} />
      </div>
      <div className="action-row">
        <Button
          disabled={busy || !selected}
          onClick={() => {
            void perform(() =>
              api.platformAssignUser(selected, organization, role),
            );
          }}
        >
          Add existing user
        </Button>
        <Button
          variant="quiet"
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
        </Button>
      </div>
      {link && (
        <p className="invitation-link">
          Share this invitation: <code>{link}</code>
          <Button variant="quiet" onClick={() => setLink("")}>
            Dismiss invitation
          </Button>
        </p>
      )}
    </section>
  );
}
