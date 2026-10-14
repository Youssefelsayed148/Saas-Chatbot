"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

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
  const [profile, setProfile] = useState<ContactProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [contacts, setContacts] = useState<api.Contact[]>([]);

  const load = useCallback(async () => {
    try {
      const item = await api.getContact(tenantId, contactId);
      setProfile(item);
      setFields(JSON.stringify(item.contact.custom_fields, null, 2));
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
    const eraseMessages = window.confirm(
      "Also erase messages in this contact's conversations?",
    );
    try {
      await api.eraseContact(tenantId, contactId, eraseMessages);
      router.push(`/app/${tenantId}/contacts`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not erase contact.",
      );
    }
  }

  if (!profile && !error) return <Loading />;
  return (
    <main className="page">
      <p>
        <Link href={`/app/${tenantId}/contacts`}>← Contacts</Link>
      </p>
      {error && <Notice tone="error" message={error} />}
      {profile && (
        <>
          <h1>{profile.contact.display_name || "Unnamed contact"}</h1>
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
              <button type="button" onClick={() => void erase()}>
                Erase contact
              </button>
            </section>
          )}
        </>
      )}
    </main>
  );
}
