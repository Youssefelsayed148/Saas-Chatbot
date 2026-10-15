"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api";
import type { ContactProfile } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Loading, Notice } from "@/lib/ui";

export default function ContactPage() {
  const { tenant: tenantId, contactId } = useParams<{
    tenant: string;
    contactId: string;
  }>();
  const router = useRouter();
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
  const canErase = roleSatisfies(role, "admin");
  const eraseDialog = useRef<HTMLDialogElement>(null);
  const [eraseMessages, setEraseMessages] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [profile, setProfile] = useState<ContactProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [contacts, setContacts] = useState<api.Contact[]>([]);
  const [followUps, setFollowUps] = useState<api.FollowUp[]>([]);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [sendAt, setSendAt] = useState("");
  const [followUpText, setFollowUpText] = useState("");

  const load = useCallback(async () => {
    try {
      const [item, scheduled] = await Promise.all([
        api.getContact(tenantId, contactId),
        api.listFollowUps(tenantId),
      ]);
      setProfile(item);
      setFields(JSON.stringify(item.contact.custom_fields, null, 2));
      setFollowUps(
        scheduled.follow_ups.filter(
          (followUp) => followUp.contact_id === contactId,
        ),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load contact.",
      );
    }
  }, [tenantId, contactId]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
      if (canEdit)
        void api
          .listContacts(tenantId)
          .then(setContacts)
          .catch(() => setContacts([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId, load, canEdit]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile) return;
    try {
      const custom_fields: Record<string, unknown> = JSON.parse(fields);
      await api.updateContact(tenantId, contactId, {
        display_name: profile.contact.display_name,
        email: profile.contact.email ?? undefined,
        phone: profile.contact.phone ?? undefined,
        stage: profile.contact.stage,
        tags: profile.contact.tags,
        custom_fields,
        consent: profile.contact.consent,
      });
      await load();
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save contact.",
      );
    }
  }
  async function merge() {
    if (!mergeTarget) return;
    try {
      await api.mergeContact(tenantId, contactId, mergeTarget);
      router.push(`/app/${tenantId}/contacts/${mergeTarget}`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not merge contact.",
      );
    }
  }
  async function erase() {
    try {
      await api.eraseContact(tenantId, contactId, eraseMessages);
      router.push(`/app/${tenantId}/contacts`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not erase contact.",
      );
    }
  }
  async function scheduleFollowUp(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedConversation || !sendAt) return;
    try {
      await api.createFollowUp(tenantId, {
        conversation_id: selectedConversation,
        contact_id: contactId,
        send_at: new Date(sendAt).toISOString(),
        text: followUpText,
      });
      setFollowUpText("");
      await load();
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not schedule follow-up.",
      );
    }
  }
  async function cancelFollowUp(followUpId: string) {
    try {
      await api.cancelFollowUp(tenantId, followUpId);
      await load();
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not cancel follow-up.",
      );
    }
  }

  if (!profile && !error) return <Loading />;
  return (
    <main className="contact-profile">
      <p>
        <Link href={`/app/${tenantId}/contacts`}>← Contacts</Link>
      </p>
      {error && <Notice tone="error" message={error} />}
      {notice && <Notice message={notice} />}
      {profile && (
        <>
          <h1 dir="auto">
            {profile.contact.display_name || "Unnamed contact"}
          </h1>
          <p className="page-purpose">
            Review this contact, update their profile and coordinate follow-ups.
          </p>
          <form onSubmit={save} className="card">
            <label>
              Name{" "}
              <input
                disabled={!canEdit}
                value={profile.contact.display_name}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact: {
                      ...profile.contact,
                      display_name: e.target.value,
                    },
                  })
                }
              />
            </label>
            <label>
              Email{" "}
              <input
                disabled={!canEdit}
                type="email"
                value={profile.contact.email ?? ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact: {
                      ...profile.contact,
                      email: e.target.value || null,
                    },
                  })
                }
              />
            </label>
            <label>
              Phone{" "}
              <input
                disabled={!canEdit}
                value={profile.contact.phone ?? ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact: {
                      ...profile.contact,
                      phone: e.target.value || null,
                    },
                  })
                }
              />
            </label>
            <label>
              Stage{" "}
              <input
                disabled={!canEdit}
                value={profile.contact.stage}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact: { ...profile.contact, stage: e.target.value },
                  })
                }
              />
            </label>
            <label>
              Tags (comma separated){" "}
              <input
                disabled={!canEdit}
                value={profile.contact.tags.join(", ")}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact: {
                      ...profile.contact,
                      tags: e.target.value
                        .split(",")
                        .map((tag) => tag.trim())
                        .filter(Boolean),
                    },
                  })
                }
              />
            </label>
            <label>
              Custom fields (JSON, up to 20 keys){" "}
              <textarea
                disabled={!canEdit}
                rows={6}
                value={fields}
                onChange={(e) => setFields(e.target.value)}
              />
            </label>
            {canEdit && <button type="submit">Save contact</button>}
          </form>
          <section>
            <h2>Channel identities</h2>
            {profile.identities.length ? (
              <ul>
                {profile.identities.map((identity) => (
                  <li key={`${identity.channel}:${identity.external_id}`}>
                    {identity.channel}: {identity.external_id}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No linked channel identities.</p>
            )}
          </section>
          <section>
            <h2>Timeline</h2>
            {profile.timeline.length ? (
              <ol>
                {profile.timeline.map((item, index) => (
                  <li
                    key={`${item.type}:${item.id ?? item.conversation_id}:${index}`}
                  >
                    {item.type === "conversation"
                      ? `${item.channel} conversation · ${item.status}`
                      : `Note: ${item.text}`}{" "}
                    · {new Date(item.created_at).toLocaleString()}
                  </li>
                ))}
              </ol>
            ) : (
              <p>No conversations or notes.</p>
            )}
          </section>
          <section className="card">
            <h2>Website follow-ups</h2>
            {canEdit &&
              profile.timeline.some(
                (item) => item.type === "conversation" && item.id,
              ) && (
                <form onSubmit={scheduleFollowUp}>
                  <label>
                    Conversation{" "}
                    <select
                      required
                      value={selectedConversation}
                      onChange={(e) => setSelectedConversation(e.target.value)}
                    >
                      <option value="">Choose conversation</option>
                      {profile.timeline
                        .filter(
                          (item) => item.type === "conversation" && item.id,
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.channel} Â· {item.status} Â·{" "}
                            {new Date(item.created_at).toLocaleDateString()}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Send after{" "}
                    <input
                      type="datetime-local"
                      required
                      value={sendAt}
                      onChange={(e) => setSendAt(e.target.value)}
                    />
                  </label>
                  <label>
                    Message{" "}
                    <textarea
                      required
                      minLength={1}
                      maxLength={4000}
                      value={followUpText}
                      onChange={(e) => setFollowUpText(e.target.value)}
                    />
                  </label>
                  <button type="submit">Schedule follow-up</button>
                </form>
              )}
            {followUps.length > 0 ? (
              <ul>
                {followUps.map((followUp) => (
                  <li key={followUp.id}>
                    {followUp.status} Â·{" "}
                    {new Date(followUp.send_at).toLocaleString()} Â·{" "}
                    {followUp.text}{" "}
                    {canEdit &&
                      ["scheduled", "ready"].includes(followUp.status) && (
                        <button
                          type="button"
                          onClick={() => void cancelFollowUp(followUp.id)}
                        >
                          Cancel
                        </button>
                      )}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No follow-ups scheduled for this contact.</p>
            )}
            <p>
              Website follow-ups appear in the visitor’s thread when the widget
              next loads the conversation. No message is pushed.
            </p>
          </section>
          {roleSatisfies(role, "admin") && (
            <section className="card">
              <h2>Merge contacts</h2>
              <label>
                Move this contact into{" "}
                <select
                  value={mergeTarget}
                  onChange={(e) => setMergeTarget(e.target.value)}
                >
                  <option value="">Choose contact</option>
                  {contacts
                    .filter((item) => item.id !== contactId)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.display_name ||
                          item.email ||
                          item.phone ||
                          item.id}
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                disabled={!mergeTarget}
                onClick={() => void merge()}
              >
                Merge into selected contact
              </button>
            </section>
          )}
          {canErase && (
            <section className="card">
              <h2>Erase contact</h2>
              <p>
                Deletes the contact and its channel identities. You can also
                erase conversation messages.
              </p>
              <button
                className="danger-button"
                type="button"
                onClick={() => eraseDialog.current?.showModal()}
              >
                Erase contact
              </button>
              <dialog ref={eraseDialog} aria-labelledby="erase-contact-title">
                <h2 id="erase-contact-title">Erase this contact?</h2>
                <p>The contact and its channel identities will be removed.</p>
                <label className="check-control">
                  <input
                    type="checkbox"
                    checked={eraseMessages}
                    onChange={(event) => setEraseMessages(event.target.checked)}
                  />
                  Also erase messages in this contact?s conversations
                </label>
                <div className="action-row">
                  <button
                    type="button"
                    className="quiet-button"
                    autoFocus
                    onClick={() => eraseDialog.current?.close()}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    onClick={() => {
                      eraseDialog.current?.close();
                      void erase();
                    }}
                  >
                    Confirm erasure
                  </button>
                </div>
              </dialog>
            </section>
          )}
        </>
      )}
    </main>
  );
}
