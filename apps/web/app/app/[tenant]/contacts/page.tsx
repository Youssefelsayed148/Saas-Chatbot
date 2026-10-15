"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import type { Contact } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";

export default function ContactsPage() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const { roleIn } = useSession();
  const canEdit = roleSatisfies(roleIn(tenantId), "editor");
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setContacts(await api.listContacts(tenantId));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load contacts.",
      );
    }
  }, [tenantId]);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await api.createContact(tenantId, {
        display_name: name,
        email: email || undefined,
        phone: phone || undefined,
      });
      setName("");
      setEmail("");
      setPhone("");
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not create contact.",
      );
    }
  }

  return (
    <main className="contacts-page">
      <h1>Contacts</h1>
      <p className="page-purpose">
        Keep visitor details, consent and conversation history together.
      </p>
      <p>
        Contact records, consent, stages, and conversation history for this
        organization.
      </p>
      {error && <Notice tone="error" message={error} />}
      {canEdit && (
        <form onSubmit={create} className="card">
          <h2>Add contact</h2>
          <label>
            Name{" "}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
            />
          </label>
          <label>
            Email{" "}
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Phone{" "}
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              maxLength={64}
            />
          </label>
          <button type="submit" disabled={!email && !phone}>
            Create contact
          </button>
        </form>
      )}
      {contacts === null ? (
        <Loading />
      ) : contacts.length === 0 ? (
        <Empty>
          Contacts captured through the widget lead form will appear here.
        </Empty>
      ) : (
        <>
          <p>{contacts.length} contacts</p>
          <p>
            <a href={`/api/v1/tenants/${tenantId}/contacts/export.csv`}>
              Export CSV
            </a>
          </p>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Stage</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((contact) => (
                <tr key={contact.id}>
                  <td dir="auto">
                    <Link href={`/app/${tenantId}/contacts/${contact.id}`}>
                      {contact.display_name || "Unnamed contact"}
                    </Link>
                  </td>
                  <td>{contact.email}</td>
                  <td>{contact.phone}</td>
                  <td>
                    <LabelBadge value={contact.stage} />
                  </td>
                  <td>{new Date(contact.updated_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
