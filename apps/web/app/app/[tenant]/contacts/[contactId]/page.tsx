"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api";
import type { ContactProfile } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  Field,
  FormSection,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";
import { Icon } from "@/lib/icons";

import "@/app/contacts-screen.css";

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
  const conversations = profile
    ? profile.timeline.filter((item) => item.type === "conversation" && item.id)
    : [];
  return (
    <main className="contact-profile contacts-page">
      <PageHeader
        eyebrow={
          <Link href={`/app/${tenantId}/contacts`}>
            <Icon name="arrow-left" /> Contacts
          </Link>
        }
        title={
          profile ? (
            <bdi>{profile.contact.display_name || "Unnamed contact"}</bdi>
          ) : (
            "Contact"
          )
        }
        purpose="Review this contact, update their profile and coordinate follow-ups."
      />
      {error && (
        <Notice
          tone="error"
          message={error}
          scope={profile ? "item" : "page"}
        />
      )}
      {notice && <Notice message={notice} />}
      {profile && (
        <>
          <FormSection
            title="Profile"
            description="Name, contact details, stage and tags."
          >
            <form onSubmit={save} className="contacts-form">
              <Field label="Name">
                {(control) => (
                  <input
                    {...control}
                    dir="auto"
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
                )}
              </Field>
              <Field label="Email">
                {(control) => (
                  <input
                    {...control}
                    dir="ltr"
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
                )}
              </Field>
              <Field label="Phone">
                {(control) => (
                  <input
                    {...control}
                    dir="ltr"
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
                )}
              </Field>
              <Field label="Stage">
                {(control) => (
                  <input
                    {...control}
                    dir="auto"
                    disabled={!canEdit}
                    value={profile.contact.stage}
                    onChange={(e) =>
                      setProfile({
                        ...profile,
                        contact: { ...profile.contact, stage: e.target.value },
                      })
                    }
                  />
                )}
              </Field>
              <Field label="Tags (comma separated)" className="contacts-wide">
                {(control) => (
                  <input
                    {...control}
                    dir="auto"
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
                )}
              </Field>
              <Field
                label="Custom fields (JSON, up to 20 keys)"
                className="contacts-wide"
              >
                {(control) => (
                  <textarea
                    {...control}
                    className="contacts-json"
                    dir="auto"
                    disabled={!canEdit}
                    rows={6}
                    value={fields}
                    onChange={(e) => setFields(e.target.value)}
                  />
                )}
              </Field>
              {canEdit && (
                <div className="contacts-wide contacts-actions">
                  <Button type="submit">Save contact</Button>
                </div>
              )}
            </form>
          </FormSection>
          <Card title="Channel identities">
            {profile.identities.length ? (
              <ul className="contacts-list">
                {profile.identities.map((identity) => (
                  <li key={`${identity.channel}:${identity.external_id}`}>
                    {identity.channel}:{" "}
                    <bdi dir="ltr">{identity.external_id}</bdi>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No linked channel identities.</p>
            )}
          </Card>
          <Card title="Timeline">
            {profile.timeline.length ? (
              <ol className="contacts-list contacts-timeline">
                {profile.timeline.map((item, index) => (
                  <li
                    key={`${item.type}:${item.id ?? item.conversation_id}:${index}`}
                  >
                    {item.type === "conversation" ? (
                      `${item.channel} conversation · ${item.status}`
                    ) : (
                      <>
                        Note: <bdi dir="auto">{item.text}</bdi>
                      </>
                    )}{" "}
                    · {new Date(item.created_at).toLocaleString()}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">No conversations or notes.</p>
            )}
          </Card>
          <Card title="Website follow-ups">
            {canEdit && conversations.length > 0 && (
              <form onSubmit={scheduleFollowUp} className="contacts-form">
                <Field label="Conversation">
                  {(control) => (
                    <select
                      {...control}
                      aria-label="Conversation"
                      required
                      value={selectedConversation}
                      onChange={(e) => setSelectedConversation(e.target.value)}
                    >
                      <option value="">Choose conversation</option>
                      {conversations.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.channel} · {item.status} ·{" "}
                          {new Date(item.created_at).toLocaleDateString()}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Send after">
                  {(control) => (
                    <input
                      {...control}
                      type="datetime-local"
                      required
                      value={sendAt}
                      onChange={(e) => setSendAt(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Message" className="contacts-wide">
                  {(control) => (
                    <textarea
                      {...control}
                      dir="auto"
                      required
                      minLength={1}
                      maxLength={4000}
                      value={followUpText}
                      onChange={(e) => setFollowUpText(e.target.value)}
                    />
                  )}
                </Field>
                <div className="contacts-wide contacts-actions">
                  <Button type="submit">Schedule follow-up</Button>
                </div>
              </form>
            )}
            {followUps.length > 0 ? (
              <ul className="contacts-list contacts-followups">
                {followUps.map((followUp) => (
                  <li key={followUp.id}>
                    <span>
                      {followUp.status} ·{" "}
                      {new Date(followUp.send_at).toLocaleString()} ·{" "}
                      <bdi dir="auto">{followUp.text}</bdi>
                    </span>{" "}
                    {canEdit &&
                      ["scheduled", "ready"].includes(followUp.status) && (
                        <Button
                          variant="quiet"
                          onClick={() => void cancelFollowUp(followUp.id)}
                        >
                          Cancel
                        </Button>
                      )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No follow-ups scheduled for this contact.</p>
            )}
            <p className="field-hint">
              Website follow-ups appear in the visitor’s thread when the widget
              next loads the conversation. No message is pushed.
            </p>
          </Card>
          {roleSatisfies(role, "admin") && (
            <Card title="Merge contacts">
              <div className="contacts-form">
                <Field label="Move this contact into" className="contacts-wide">
                  {(control) => (
                    <select
                      {...control}
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
                  )}
                </Field>
                <div className="contacts-wide contacts-actions">
                  <Button disabled={!mergeTarget} onClick={() => void merge()}>
                    Merge into selected contact
                  </Button>
                </div>
              </div>
            </Card>
          )}
          {canErase && (
            <Card title="Erase contact" className="danger-zone">
              <p>
                Deletes the contact and its channel identities. You can also
                erase conversation messages.
              </p>
              <div className="contacts-actions">
                <Button
                  variant="danger"
                  onClick={() => eraseDialog.current?.showModal()}
                >
                  Erase contact
                </Button>
              </div>
              <dialog
                ref={eraseDialog}
                className="ui-dialog contacts-dialog"
                aria-labelledby="erase-contact-title"
              >
                <h2 id="erase-contact-title">Erase this contact?</h2>
                <p>The contact and its channel identities will be removed.</p>
                <label className="check-control">
                  <input
                    type="checkbox"
                    checked={eraseMessages}
                    onChange={(event) => setEraseMessages(event.target.checked)}
                  />
                  Also erase messages in this contact’s conversations
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
            </Card>
          )}
        </>
      )}
    </main>
  );
}
