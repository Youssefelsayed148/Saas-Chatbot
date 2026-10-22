"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import type { Bot } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ConfirmAction, Loading, Notice } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import RagTierControl from "@/lib/rag-tier-control";

/** API field paths (dotted, without the body root) → form input keys.
 * Unmatched fields render in the form-level error area instead. */
const FIELD_KEYS = new Set([
  "name",
  "assistant_name",
  "business_name",
  "business_description",
  "welcome_message.en",
  "welcome_message.ar",
  "opening_questions",
  "default_language",
  "support_email",
  "support_phone",
  "colour",
  "avatar",
  "position",
  "handoff_enabled",
  "allowed_domains",
]);

function inlineFieldKey(field: string): string | null {
  let key = field.replace(/^config\./, "");
  const parts = key.split(".");
  // List entries validate per item ("allowed_domains.0"); show under the list.
  if (/^\d+$/.test(parts[parts.length - 1])) parts.pop();
  key = parts.join(".");
  return FIELD_KEYS.has(key) ? key : null;
}

export default function BotSettingsPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { me, staffOrganizations } = useSession();
  const canEdit = !!me?.is_platform_staff;

  const [bot, setBot] = useState<Bot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  const [name, setName] = useState("");
  const [assistantName, setAssistantName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessDescription, setBusinessDescription] = useState("");
  const [welcomeEn, setWelcomeEn] = useState("");
  const [welcomeAr, setWelcomeAr] = useState("");
  const [openingQuestions, setOpeningQuestions] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState<"en" | "ar">("en");
  const [supportEmail, setSupportEmail] = useState("");
  const [supportPhone, setSupportPhone] = useState("");
  const [colour, setColour] = useState("");
  const [avatar, setAvatar] = useState("");
  const [position, setPosition] = useState<"left" | "right" | "">("");
  const [handoffEnabled, setHandoffEnabled] = useState(true);
  const [allowedDomains, setAllowedDomains] = useState("");

  const load = useCallback(async () => {
    try {
      const loaded = await api.getBot(tenantId, botId);
      setBot(loaded);
      setName(loaded.name);
      setAssistantName(loaded.config.assistant_name ?? "");
      setBusinessName(loaded.config.business_name ?? "");
      setBusinessDescription(loaded.config.business_description ?? "");
      setWelcomeEn(loaded.config.welcome_message?.en ?? "");
      setWelcomeAr(loaded.config.welcome_message?.ar ?? "");
      setOpeningQuestions((loaded.config.opening_questions ?? []).join("\n"));
      setDefaultLanguage(loaded.config.default_language ?? "en");
      setSupportEmail(loaded.config.support_email ?? "");
      setSupportPhone(loaded.config.support_phone ?? "");
      setColour(loaded.config.colour ?? "");
      setAvatar(loaded.config.avatar ?? "");
      setPosition(loaded.config.position ?? "");
      setHandoffEnabled(loaded.config.handoff_enabled ?? true);
      setAllowedDomains((loaded.config.allowed_domains ?? []).join("\n"));
      setLoadError(null);
    } catch (caught) {
      setLoadError(
        caught instanceof Error ? caught.message : "Could not load this bot.",
      );
    }
  }, [tenantId, botId]);

  useEffect(() => {
    if (!canEdit) return;
    // Loaders run deferred so no state updates synchronously in the effect.
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load, canEdit]);

  async function onSave(event: React.FormEvent) {
    event.preventDefault();
    setSaveError(null);
    setFieldErrors({});
    setSaved(false);
    setSaving(true);
    try {
      const config: Record<string, unknown> = {};
      if (assistantName) config.assistant_name = assistantName;
      if (businessName) config.business_name = businessName;
      if (businessDescription)
        config.business_description = businessDescription;
      if (welcomeEn || welcomeAr) {
        config.welcome_message = {
          ...(welcomeEn ? { en: welcomeEn } : {}),
          ...(welcomeAr ? { ar: welcomeAr } : {}),
        };
      }
      if (openingQuestions) {
        config.opening_questions = openingQuestions
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
      }
      config.default_language = defaultLanguage;
      if (supportEmail) config.support_email = supportEmail;
      if (supportPhone) config.support_phone = supportPhone;
      if (colour) config.colour = colour;
      if (avatar) config.avatar = avatar;
      if (position) config.position = position;
      config.handoff_enabled = handoffEnabled;
      if (allowedDomains) {
        config.allowed_domains = allowedDomains
          .split("\n")
          .map((line) => line.trim().toLowerCase())
          .filter(Boolean);
      }
      const updated = await api.patchBot(tenantId, botId, {
        name,
        config,
      });
      setBot(updated);
      setSaved(true);
      await load();
    } catch (caught) {
      if (caught instanceof api.ApiError && caught.fieldErrors.length > 0) {
        // Field details go inline under the matching input; fields without a
        // matching input fall back to the form-level error area.
        const mapped: Record<string, string> = {};
        for (const entry of caught.fieldErrors) {
          const key = inlineFieldKey(entry.field);
          if (key && !(key in mapped)) mapped[key] = entry.message;
          else if (!key) setSaveError(caught.message);
        }
        setFieldErrors(mapped);
        if (!Object.keys(mapped).length) setSaveError(caught.message);
      } else {
        setSaveError(
          caught instanceof Error ? caught.message : "Could not save settings.",
        );
      }
    } finally {
      setSaving(false);
    }
  }

  async function transitionTo(status: "active" | "paused") {
    setTransitioning(true);
    setSaveError(null);
    try {
      const updated = await api.patchBot(tenantId, botId, { status });
      setBot(updated);
      await load();
    } catch (caught) {
      setSaveError(
        caught instanceof Error
          ? caught.message
          : "Could not update the bot status.",
      );
    } finally {
      setTransitioning(false);
    }
  }

  if (!me?.is_platform_staff) return null;

  function fieldError(key: string) {
    const message = fieldErrors[key];
    if (!message) return null;
    return (
      <p role="alert" data-testid={`field-error-${key}`}>
        {message}
      </p>
    );
  }

  if (loadError) {
    return (
      <main>
        <Notice message={loadError} tone="error" />
        <Link href={`/app/${tenantId}/bots`}>Back to bots</Link>
      </main>
    );
  }
  if (!bot) {
    return (
      <main>
        <Loading label="Loading bot…" />
      </main>
    );
  }

  return (
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1>{bot.name} — settings</h1>
      <p>
        Organization:{" "}
        {staffOrganizations?.find((org) => org.id === tenantId)?.name ??
          "Current organization"}{" "}
        (read-only)
      </p>
      <p className="page-purpose">
        Configure your assistant, appearance and website access. Save settings
        applies appearance changes live.
      </p>
      <div data-status={bot.status}>
        Status: <LabelBadge value={bot.status} />
        {canEdit && bot.status !== "archived" && (
          <div>
            {" "}
            {bot.status !== "active" && (
              <button
                type="button"
                data-testid="activate-bot"
                disabled={transitioning}
                onClick={() => void transitionTo("active")}
              >
                {transitioning ? "Activating…" : "Activate bot"}
              </button>
            )}
            {bot.status === "active" && (
              <ConfirmAction
                title="Pause bot?"
                description={
                  "The website widget will become unavailable and this bot will stop answering visitors until activated again."
                }
                testId="pause-bot"
                disabled={transitioning}
                onConfirm={() => void transitionTo("paused")}
              >
                {transitioning ? "Pausing…" : "Pause bot"}
              </ConfirmAction>
            )}
          </div>
        )}
      </div>
      {bot.widget_locator && (
        <p className="muted">
          Widget locator:{" "}
          <code data-testid="settings-locator">{bot.widget_locator}</code>
        </p>
      )}
      {!canEdit && (
        <Notice message="Only platform operators can edit bot settings." />
      )}
      <form onSubmit={onSave}>
        <label>
          Bot name
          <input
            name="name"
            disabled={!canEdit}
            required
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        {fieldError("name")}
        <label>
          Assistant name
          <input
            name="assistant_name"
            disabled={!canEdit}
            maxLength={100}
            value={assistantName}
            onChange={(event) => setAssistantName(event.target.value)}
          />
        </label>
        {fieldError("assistant_name")}
        <label>
          Business name
          <input
            name="business_name"
            disabled={!canEdit}
            maxLength={100}
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
          />
        </label>
        {fieldError("business_name")}
        <label>
          Business description
          <textarea
            dir="auto"
            name="business_description"
            disabled={!canEdit}
            rows={3}
            maxLength={1000}
            value={businessDescription}
            onChange={(event) => setBusinessDescription(event.target.value)}
          />
        </label>
        {fieldError("business_description")}
        <label>
          Welcome message (EN)
          <input
            name="welcome_en"
            disabled={!canEdit}
            maxLength={500}
            value={welcomeEn}
            onChange={(event) => setWelcomeEn(event.target.value)}
          />
        </label>
        {fieldError("welcome_message.en")}
        <label>
          Welcome message (AR)
          <input
            name="welcome_ar"
            dir="auto"
            disabled={!canEdit}
            maxLength={500}
            value={welcomeAr}
            onChange={(event) => setWelcomeAr(event.target.value)}
          />
        </label>
        {fieldError("welcome_message.ar")}
        <label>
          Opening questions (one per line, max 10)
          <textarea
            dir="auto"
            name="opening_questions"
            disabled={!canEdit}
            rows={4}
            value={openingQuestions}
            onChange={(event) => setOpeningQuestions(event.target.value)}
          />
        </label>
        {fieldError("opening_questions")}
        <label>
          Default language
          <select
            name="default_language"
            disabled={!canEdit}
            value={defaultLanguage}
            onChange={(event) =>
              setDefaultLanguage(event.target.value as "en" | "ar")
            }
          >
            <option value="en">English</option>
            <option value="ar">العربية</option>
          </select>
        </label>
        {fieldError("default_language")}
        <label>
          Support email
          <input
            name="support_email"
            type="email"
            disabled={!canEdit}
            value={supportEmail}
            onChange={(event) => setSupportEmail(event.target.value)}
          />
        </label>
        {fieldError("support_email")}
        <label>
          Support phone
          <input
            name="support_phone"
            disabled={!canEdit}
            maxLength={30}
            value={supportPhone}
            onChange={(event) => setSupportPhone(event.target.value)}
          />
        </label>
        {fieldError("support_phone")}
        <label>
          Widget colour (hex, e.g. #1a2b3c)
          <input
            name="colour"
            disabled={!canEdit}
            value={colour}
            onChange={(event) => setColour(event.target.value)}
          />
        </label>
        {fieldError("colour")}
        <label>
          Widget avatar (public http(s) image URL)
          <input
            name="avatar"
            disabled={!canEdit}
            value={avatar}
            onChange={(event) => setAvatar(event.target.value)}
          />
        </label>
        {fieldError("avatar")}
        <label>
          Widget position
          <select
            name="position"
            disabled={!canEdit}
            value={position}
            onChange={(event) =>
              setPosition(event.target.value as "left" | "right" | "")
            }
          >
            <option value="">(none)</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
          </select>
        </label>
        {fieldError("position")}
        <label>
          Human handoff enabled
          <input
            name="handoff_enabled"
            type="checkbox"
            disabled={!canEdit}
            checked={handoffEnabled}
            onChange={(event) => setHandoffEnabled(event.target.checked)}
          />
        </label>
        {fieldError("handoff_enabled")}
        <label>
          Allowed domains (one per line, max 50)
          <textarea
            dir="auto"
            name="allowed_domains"
            disabled={!canEdit}
            rows={3}
            value={allowedDomains}
            onChange={(event) => setAllowedDomains(event.target.value)}
          />
        </label>
        {fieldError("allowed_domains")}
        {saveError && <Notice message={saveError} tone="error" />}
        {saved && <Notice message="Settings saved." />}
        {canEdit && (
          <button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </button>
        )}
      </form>
      {canEdit && <RagTierControl tenantId={tenantId} botId={botId} />}
      {bot.status === "archived" && <Notice message="This bot is archived." />}
    </main>
  );
}
