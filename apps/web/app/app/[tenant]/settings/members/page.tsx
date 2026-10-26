"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { Invitation, Member, Role } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  ConfirmAction,
  DataTable,
  Empty,
  Field,
  FormSection,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";

import "@/app/team-screen.css";

const CHANGEABLE_ROLES: Role[] = ["viewer", "editor", "admin"];
const PURPOSE = "Invite teammates and manage their access to this workspace.";

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
        <PageHeader title="Team" purpose={PURPOSE} />
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
      <PageHeader title="Team" purpose={PURPOSE} />
      {loadError && <Notice message={loadError} tone="error" />}
      {actionError && (
        <Notice message={actionError} tone="error" scope="item" />
      )}

      <FormSection
        title="Invite a teammate"
        description="They receive a one-time link. Pick the access level they should have."
      >
        <form className="team-invite" onSubmit={onInvite}>
          <Field label="Email">
            {(control) => (
              <input
                {...control}
                name="email"
                type="email"
                dir="ltr"
                required
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
              />
            )}
          </Field>
          <Field label="Role">
            {(control) => (
              <select
                {...control}
                name="role"
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as Role)}
              >
                <option value="admin">Admin</option>
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
            )}
          </Field>
          <Button type="submit" disabled={busy === "invite"}>
            {busy === "invite" ? "Creating link…" : "Create invite link"}
          </Button>
        </form>
        {newLink && (
          <p role="status" className="team-link">
            <span>One-time invite link (works once, expires in 7 days):</span>
            <code dir="ltr">{absoluteLink(newLink)}</code>
            <Button
              variant="quiet"
              onClick={async () => {
                await navigator.clipboard.writeText(absoluteLink(newLink));
                setCopied(true);
              }}
            >
              {copied ? "Copied!" : "Copy"}
            </Button>
          </p>
        )}
      </FormSection>

      <FormSection title="Pending invitations">
        {invitations === null && <Loading label="Loading invitations…" />}
        {invitations && (
          <DataTable
            caption="Invitation list"
            rows={invitations}
            rowKey={(invitation) => invitation.id}
            empty={<Empty>No pending invitations.</Empty>}
            columns={[
              {
                key: "email",
                header: "Email",
                cell: (invitation) => <bdi dir="ltr">{invitation.email}</bdi>,
              },
              {
                key: "role",
                header: "Role",
                cell: (invitation) => invitation.role,
              },
              {
                key: "status",
                header: "Status",
                cell: (invitation) =>
                  invitation.expired ? (
                    <StatusBadge value="expired" tone="warning" />
                  ) : (
                    <StatusBadge value="pending" />
                  ),
              },
              {
                key: "actions",
                header: "Actions",
                cell: (invitation) => (
                  <div className="row-actions">
                    <Button
                      variant="quiet"
                      disabled={busy === `resend-${invitation.id}`}
                      onClick={() => onResend(invitation)}
                    >
                      {busy === `resend-${invitation.id}`
                        ? "Resending…"
                        : "Resend link"}
                    </Button>
                    <Button
                      variant="quiet"
                      disabled={busy === `revoke-${invitation.id}`}
                      onClick={() => onRevoke(invitation)}
                    >
                      {busy === `revoke-${invitation.id}`
                        ? "Revoking…"
                        : "Revoke"}
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </FormSection>

      <FormSection
        title="Members"
        description="The last admin cannot be demoted or removed."
      >
        {members === null && <Loading label="Loading members…" />}
        {members && (
          <DataTable
            caption="Member list"
            rows={members}
            rowKey={(member) => member.user_id}
            empty={<Empty>No members found.</Empty>}
            columns={[
              {
                key: "email",
                header: "Email",
                cell: (member) => <bdi dir="ltr">{member.email}</bdi>,
              },
              {
                key: "role",
                header: "Role",
                cell: (member) => {
                  const isSelf = me?.id === member.user_id;
                  const isLastAdmin =
                    member.role === "admin" &&
                    members.filter((row) => row.role === "admin").length === 1;
                  return isLastAdmin ? (
                    <span title="The last admin is protected">
                      {member.role}
                    </span>
                  ) : (
                    <select
                      aria-label={`Role for ${member.email}`}
                      className="team-role-select"
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
                  );
                },
              },
              {
                key: "actions",
                header: "Actions",
                cell: (member) => {
                  const isSelf = me?.id === member.user_id;
                  const isLastAdmin =
                    member.role === "admin" &&
                    members.filter((row) => row.role === "admin").length === 1;
                  return (
                    <div className="row-actions">
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
                      {isSelf && <span className="muted">(you)</span>}
                    </div>
                  );
                },
              },
            ]}
          />
        )}
      </FormSection>
    </main>
  );
}
