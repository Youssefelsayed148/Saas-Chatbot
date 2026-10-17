"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { Invitation, Member, Role } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { ConfirmAction, Empty, Loading, Notice } from "@/lib/ui";

const CHANGEABLE_ROLES: Role[] = ["viewer", "editor", "admin"];

export default function MembersPage() {
  const params = useParams<{ tenant: string }>();
  const tenantId = params.tenant;
  const router = useRouter();
  const { me, roleIn, refresh } = useSession();
  const role = roleIn(tenantId);
  const isAdmin = roleSatisfies(role, "admin");

  const [members, setMembers] = useState<Member[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newLink, setNewLink] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("viewer");
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const [memberRows, invitationRows] = await Promise.all([
        api.listMembers(tenantId),
        api.listInvitations(tenantId),
      ]);
      setLoadError(null);
      setMembers(memberRows);
      setInvitations(invitationRows);
    } catch (caught) {
      setLoadError(
        caught instanceof Error ? caught.message : "Could not load team data.",
      );
    }
  }, [tenantId]);

  useEffect(() => {
    if (!isAdmin) return;
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [isAdmin, load]);

  function absoluteLink(linkPath: string): string {
    return `${window.location.origin}${linkPath}`;
  }

  async function onInvite(event: React.FormEvent) {
    event.preventDefault();
    setActionError(null);
    setNewLink(null);
    setBusy("invite");
    try {
      const created = await api.createInvitation(
        tenantId,
        inviteEmail,
        inviteRole,
      );
      setNewLink(created.link_path ?? null);
      setInviteEmail("");
      setCopied(false);
      await load();
    } catch (caught) {
      setActionError(
        caught instanceof Error
          ? caught.message
          : "Could not create the invitation.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function onResend(invitation: Invitation) {
    setActionError(null);
    setBusy(`resend-${invitation.id}`);
    try {
      const resent = await api.resendInvitation(tenantId, invitation.id);
      setNewLink(resent.link_path ?? null);
      setCopied(false);
      await load();
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Could not resend the link.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function onRevoke(invitation: Invitation) {
    setActionError(null);
    setBusy(`revoke-${invitation.id}`);
    try {
      await api.revokeInvitation(tenantId, invitation.id);
      await load();
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Could not revoke the link.",
      );
    } finally {
      setBusy(null);
    }
  }

  if (me && !isAdmin) {
    return (
      <main className="team-page">
        <h1>Team</h1>
        <p className="page-purpose">
          Invite teammates and manage their access to this workspace.
        </p>
        <Notice
          message={
            role
              ? `Managing the team requires the admin role (you are ${role}).`
              : "You are not a member of this organization."
          }
        />
      </main>
    );
  }

  return (
    <main className="team-page">
      <h1>Team</h1>
      <p className="page-purpose">
        Invite teammates and manage their access to this workspace.
      </p>
      {loadError && <Notice message={loadError} tone="error" />}
      {actionError && <Notice message={actionError} tone="error" />}

      <section aria-label="Invite teammate">
        <h2>Invite a teammate</h2>
        <form onSubmit={onInvite}>
          <label>
            Email
            <input
              name="email"
              type="email"
              required
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
            />
          </label>
          <label>
            Role
            <select
              name="role"
              value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value as Role)}
            >
              <option value="admin">Admin</option>
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
          </label>
          <button type="submit" disabled={busy === "invite"}>
            {busy === "invite" ? "Creating link…" : "Create invite link"}
          </button>
        </form>
        {newLink && (
          <p role="status">
            One-time invite link (works once, expires in 7 days):{" "}
            <code>{absoluteLink(newLink)}</code>{" "}
            <button
              type="button"
              onClick={async () => {
                await navigator.clipboard.writeText(absoluteLink(newLink));
                setCopied(true);
              }}
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </p>
        )}
      </section>

      <section aria-label="Pending invitations">
        <h2>Pending invitations</h2>
        {invitations === null && <Loading label="Loading invitations…" />}
        {invitations && invitations.length === 0 && (
          <Empty>No pending invitations.</Empty>
        )}
        {invitations && invitations.length > 0 && (
          <ul>
            {invitations.map((invitation) => (
              <li key={invitation.id}>
                {invitation.email} — {invitation.role}
                {invitation.expired ? " (expired)" : ""}
                <button
                  type="button"
                  disabled={busy === `resend-${invitation.id}`}
                  onClick={() => onResend(invitation)}
                >
                  {busy === `resend-${invitation.id}`
                    ? "Resending…"
                    : "Resend link"}
                </button>
                <button
                  type="button"
                  disabled={busy === `revoke-${invitation.id}`}
                  onClick={() => onRevoke(invitation)}
                >
                  {busy === `revoke-${invitation.id}` ? "Revoking…" : "Revoke"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Members">
        <h2>Members</h2>
        {members === null && <Loading label="Loading members…" />}
        {members && members.length === 0 && <Empty>No members found.</Empty>}
        {members && members.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => {
                const isSelf = me?.id === member.user_id;
                const isLastAdmin =
                  member.role === "admin" &&
                  members.filter((row) => row.role === "admin").length === 1;
                return (
                  <tr key={member.user_id}>
                    <td>{member.email}</td>
                    <td>
                      {isLastAdmin ? (
                        <span title="The last admin is protected">
                          {member.role}
                        </span>
                      ) : (
                        <select
                          aria-label={`Role for ${member.email}`}
                          value={member.role}
                          disabled={busy === `role-${member.user_id}`}
                          onChange={async (event) => {
                            const newRole = event.target.value as Role;
                            setBusy(`role-${member.user_id}`);
                            setActionError(null);
                            try {
                              await api.updateMemberRole(
                                tenantId,
                                member.user_id,
                                newRole,
                              );
                              if (isSelf && newRole !== "admin") {
                                await refresh();
                                router.replace(`/app/${tenantId}`);
                              } else await load();
                            } catch (caught) {
                              setActionError(
                                caught instanceof Error
                                  ? caught.message
                                  : "Could not change role.",
                              );
                              await load();
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          {CHANGEABLE_ROLES.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>
                      {isLastAdmin ? (
                        <span
                          className="muted"
                          title="The last admin is protected"
                        >
                          protected
                        </span>
                      ) : (
                        <ConfirmAction
                          title="Remove member?"
                          description={
                            "This member will lose access to this organization immediately."
                          }
                          disabled={busy === `remove-${member.user_id}`}
                          onConfirm={async () => {
                            setBusy(`remove-${member.user_id}`);
                            setActionError(null);
                            try {
                              await api.removeMember(tenantId, member.user_id);
                              if (isSelf) {
                                await refresh();
                                router.replace("/app");
                              } else await load();
                            } catch (caught) {
                              setActionError(
                                caught instanceof Error
                                  ? caught.message
                                  : "Could not remove member.",
                              );
                              await load();
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          {busy === `remove-${member.user_id}`
                            ? "Removing…"
                            : "Remove"}
                        </ConfirmAction>
                      )}
                      {isSelf && <span className="muted"> (you)</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <p className="muted">The last admin cannot be demoted or removed.</p>
      </section>
    </main>
  );
}
