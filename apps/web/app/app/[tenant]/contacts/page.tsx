"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { humanLabel, LabelBadge } from "@/lib/labels";
import { channelOptions } from "@/lib/insights";
import * as api from "@/lib/api";
import type { Contact } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  DataTable,
  Empty,
  Field,
  FormSection,
  LinkButton,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";

import "@/app/contacts-screen.css";

export default function ContactsPage() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const { roleIn } = useSession();
  const canEdit = roleSatisfies(roleIn(tenantId), "editor");
  const canExport = roleSatisfies(roleIn(tenantId), "admin");
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [channel, setChannel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setContacts(
        await api.listContacts(tenantId, { channel: channel || undefined }),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load contacts.",
      );
    }
  }, [tenantId, channel]);
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
      <PageHeader
        title="Contacts"
        purpose="Keep visitor details, consent and conversation history together."
        actions={
          canExport && contacts && contacts.length > 0 ? (
            <LinkButton
              variant="secondary"
              className="contacts-export"
              href={`/api/v1/tenants/${tenantId}/contacts/export.csv`}
            >
              Export CSV
            </LinkButton>
          ) : undefined
        }
      />
      {error && <Notice tone="error" message={error} />}
      {canEdit && (
        <FormSection
          title="Add contact"
          description="Contact records, consent, stages, and conversation history for this organization."
        >
          <form onSubmit={create} className="contacts-form">
            <Field label="Name">
              {(control) => (
                <input
                  {...control}
                  dir="auto"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={200}
                />
              )}
            </Field>
            <Field
              label="Email"
              hint={
                !email && !phone ? "Add an email or a phone number." : undefined
              }
            >
              {(control) => (
                <input
                  {...control}
                  type="email"
                  dir="ltr"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </Field>
            <Field label="Phone">
              {(control) => (
                <input
                  {...control}
                  dir="ltr"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  maxLength={64}
                />
              )}
            </Field>
            <Button type="submit" disabled={!email && !phone}>
              Create contact
            </Button>
          </form>
        </FormSection>
      )}
      {contacts === null ? (
        <Loading />
      ) : contacts.length === 0 && !channel ? (
        <Empty>
          Contacts captured through the widget lead form will appear here.
        </Empty>
      ) : (
        <Card
          title="All contacts"
          actions={
            <span className="contacts-count">{contacts.length} contacts</span>
          }
        >
          <Field label="Channel">
            {(control) => (
              <select
                {...control}
                data-testid="contacts-channel-filter"
                value={channel}
                onChange={(event) => setChannel(event.target.value)}
              >
                {channelOptions().map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.value === "" ? "All channels" : option.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <DataTable
            caption="Contact list"
            rows={contacts}
            rowKey={(contact) => contact.id}
            empty={<p className="muted">No contacts on this channel.</p>}
            columns={[
              {
                key: "name",
                header: "Name",
                className: "contacts-name",
                cell: (contact) => (
                  <Link href={`/app/${tenantId}/contacts/${contact.id}`}>
                    <bdi>{contact.display_name || "Unnamed contact"}</bdi>
                  </Link>
                ),
              },
              {
                key: "email",
                header: "Email",
                cell: (contact) => <bdi dir="ltr">{contact.email}</bdi>,
              },
              {
                key: "phone",
                header: "Phone",
                cell: (contact) => <bdi dir="ltr">{contact.phone}</bdi>,
              },
              {
                key: "channels",
                header: "Channels",
                cell: (contact) => (
                  <span data-testid="contact-channels">
                    {(contact.channels?.length
                      ? contact.channels
                      : contact.source_channel
                        ? [contact.source_channel]
                        : []
                    )
                      .map((value) => humanLabel(value))
                      .join(", ")}
                  </span>
                ),
              },
              {
                key: "stage",
                header: "Stage",
                cell: (contact) => <LabelBadge value={contact.stage} />,
              },
              {
                key: "updated",
                header: "Updated",
                className: "contacts-date",
                cell: (contact) =>
                  new Date(contact.updated_at).toLocaleDateString(),
              },
            ]}
          />
        </Card>
      )}
    </main>
  );
}
