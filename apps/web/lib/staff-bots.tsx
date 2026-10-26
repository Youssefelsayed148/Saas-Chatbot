"use client";

import { useState } from "react";
import * as api from "./api";
import { OrganizationSelect } from "./staff-members";
import { Button, Field, FormSection, LinkButton, Notice } from "./ui";
import "@/app/staff-screens.css";

export function BotLinks({
  organization,
  bot,
}: {
  organization: string;
  bot: string;
}) {
  return (
    <span className="bot-links">
      <LinkButton
        href={`/app/${organization}/bots/${bot}/knowledge`}
        variant="secondary"
        size="sm"
      >
        Knowledge
      </LinkButton>{" "}
      <LinkButton
        href={`/app/${organization}/bots/${bot}/settings`}
        variant="secondary"
        size="sm"
      >
        Settings
      </LinkButton>
    </span>
  );
}

export function CreateBotForm({
  organization,
  onCreated,
}: {
  organization?: { id: string; name: string };
  onCreated: () => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [created, setCreated] = useState<api.Bot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setCreated(null);
    try {
      const bot = await api.platformCreateBot(
        organization?.id ?? selected,
        name.trim(),
      );
      setCreated(bot);
      setName("");
      await onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create bot.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <FormSection
      title="Create bot"
      description="Creates a bot inside an organization. Add knowledge and settings after it exists."
    >
      {error && <Notice tone="error" message={error} />}
      <form
        onSubmit={(e) => {
          void submit(e);
        }}
      >
        {organization ? (
          <p>
            Organization: <strong>{organization.name}</strong> (fixed)
          </p>
        ) : (
          <OrganizationSelect value={selected} onChange={setSelected} />
        )}
        <Field label="Bot name">
          {(control) => (
            <input
              {...control}
              required
              minLength={1}
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create bot"}
        </Button>
      </form>
      {created && (
        <div role="status" className="bot-created">
          <h3>Bot created — next steps</h3>
          <p>
            Upload and publish knowledge, then configure the allowed website
            domains in Settings.
          </p>
          <BotLinks organization={created.tenant_id} bot={created.id} />
        </div>
      )}
    </FormSection>
  );
}
