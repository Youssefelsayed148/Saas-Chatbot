"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import type { Bot } from "@/lib/api";
import { normalizeDomainLines } from "@/lib/domains";
import { useSession } from "@/lib/session";
import {
  Button,
  Card,
  ConfirmAction,
  Field,
  FormSection,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import RagTierControl from "@/lib/rag-tier-control";
import BotToneField from "@/lib/bot-tone-field";
import BotReadinessCard from "@/lib/bot-readiness-card";
import WidgetThemeEditor, { type ThemeDraft } from "@/lib/widget-theme-editor";
import WidgetPreview from "@/lib/widget-preview";
import { THEME_SLOTS, isHex, type ThemeSlots } from "@/lib/widget-theme";
import "@/app/bot-settings-c.css";
import "@/app/settings-screen.css";

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
  "tone_and_rules",
  "theme",
]);

function inlineFieldKey(field: string): string | null {
  let key = field.replace(/^config\./, "");
  const parts = key.split(".");
  // List entries validate per item ("allowed_domains.0"); show under the list.
  if (/^\d+$/.test(parts[parts.length - 1])) parts.pop();
  // Theme slot errors ("theme.header") show under the appearance editor.
  if (parts[0] === "theme") parts.length = 1;
  key = parts.join(".");
  // One name field (#9): a bot-name error shows under "Assistant name".
  if (key === "name") key = "assistant_name";
  return FIELD_KEYS.has(key) ? key : null;
}

/** Everything the Save settings button sends, as one comparable string, so a
 * change that is reverted reads as up to date again (presentation only). */
function formSnapshot(values: Record<string, unknown>): string {
  return JSON.stringify(values);
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
  // Presentation only (#24): the form values as last loaded or saved; the form
  // is dirty while it differs from this. The instantly saved AI tier control is
  // separate.
  const [baseline, setBaseline] = useState<string | null>(null);
  const [readinessKey, setReadinessKey] = useState(0);
  const [transitioning, setTransitioning] = useState(false);

  const [assistantName, setAssistantName] = useState("");
  // null = not edited: the field then shows the organization name (#9).
  const [businessNameEdit, setBusinessNameEdit] = useState<string | null>(null);
  const organizationName =
    staffOrganizations?.find((org) => org.id === tenantId)?.name ?? "";
  const businessName = businessNameEdit ?? organizationName;
  const [businessDescription, setBusinessDescription] = useState("");
  const [welcomeEn, setWelcomeEn] = useState("");
  const [welcomeAr, setWelcomeAr] = useState("");
  const [openingQuestions, setOpeningQuestions] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState<"en" | "ar">("en");
  const [supportEmail, setSupportEmail] = useState("");
  const [supportPhone, setSupportPhone] = useState("");
  const [colour, setColour] = useState("");
  const [avatar, setAvatar] = useState("");
  const [position, setPosition] = useState<"left" | "right">("right");
  const [handoffEnabled, setHandoffEnabled] = useState(true);
  const [allowedDomains, setAllowedDomains] = useState("");
  const [toneAndRules, setToneAndRules] = useState("");
  const [themeDraft, setThemeDraft] = useState<ThemeDraft>({
    preset: "classic",
    slots: {},
  });
  // Only send a theme when staff changed it or the bot already had one, so an
  // untouched bot keeps the exact default payload.
  const [themeActive, setThemeActive] = useState(false);

  const load = useCallback(async () => {
    try {
      const loaded = await api.getBot(tenantId, botId);
      setBot(loaded);
      // One name field (#9): the legacy bot name is the fallback.
      setAssistantName(loaded.config.assistant_name || loaded.name);
      setBusinessNameEdit(loaded.config.business_name || null);
      setBusinessDescription(loaded.config.business_description ?? "");
      setWelcomeEn(loaded.config.welcome_message?.en ?? "");
      setWelcomeAr(loaded.config.welcome_message?.ar ?? "");
      setOpeningQuestions((loaded.config.opening_questions ?? []).join("\n"));
      setDefaultLanguage(loaded.config.default_language ?? "en");
      setSupportEmail(loaded.config.support_email ?? "");
      setSupportPhone(loaded.config.support_phone ?? "");
      setColour(loaded.config.colour ?? "");
      setAvatar(loaded.config.avatar ?? "");
      setPosition(loaded.config.position ?? "right");
      setHandoffEnabled(loaded.config.handoff_enabled ?? true);
      setAllowedDomains((loaded.config.allowed_domains ?? []).join("\n"));
      setToneAndRules(loaded.tone_and_rules ?? "");
      const storedTheme = loaded.config.theme;
      const slots: ThemeSlots = {};
      for (const slot of THEME_SLOTS) {
        const value = storedTheme?.[slot];
        if (isHex(value)) slots[slot] = value;
      }
      const loadedTheme: ThemeDraft = {
        preset:
          storedTheme?.preset ??
          (Object.keys(slots).length > 0 ? "custom" : "classic"),
        slots,
      };
      setThemeDraft(loadedTheme);
      setThemeActive(!!storedTheme);
      setBaseline(
        formSnapshot({
          assistantName: loaded.config.assistant_name || loaded.name,
          businessName: loaded.config.business_name || "",
          businessDescription: loaded.config.business_description ?? "",
          welcomeEn: loaded.config.welcome_message?.en ?? "",
          welcomeAr: loaded.config.welcome_message?.ar ?? "",
          openingQuestions: (loaded.config.opening_questions ?? []).join("\n"),
          defaultLanguage: loaded.config.default_language ?? "en",
          supportEmail: loaded.config.support_email ?? "",
          supportPhone: loaded.config.support_phone ?? "",
          colour: loaded.config.colour ?? "",
          avatar: loaded.config.avatar ?? "",
          position: loaded.config.position ?? "right",
          handoffEnabled: loaded.config.handoff_enabled ?? true,
          allowedDomains: (loaded.config.allowed_domains ?? []).join("\n"),
          toneAndRules: loaded.tone_and_rules ?? "",
          themeDraft: loadedTheme,
          themeActive: !!storedTheme,
        }),
      );
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
      config.assistant_name = assistantName;
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
      if (themeActive) {
        config.theme = { preset: themeDraft.preset, ...themeDraft.slots };
      }
      if (allowedDomains) {
        config.allowed_domains = normalizeDomainLines(allowedDomains);
      }
      const updated = await api.patchBot(tenantId, botId, {
        // The stored bot name follows the single Assistant name field.
        name: assistantName,
        config,
        tone_and_rules: toneAndRules,
      });
      setBot(updated);
      setSaved(true);
      await load();
      setReadinessKey((key) => key + 1);
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

  const dirty =
    baseline !== null &&
    formSnapshot({
      assistantName,
      businessName: businessNameEdit ?? "",
      businessDescription,
      welcomeEn,
      welcomeAr,
      openingQuestions,
      defaultLanguage,
      supportEmail,
      supportPhone,
      colour,
      avatar,
      position,
      handoffEnabled,
      allowedDomains,
      toneAndRules,
      themeDraft,
      themeActive,
    }) !== baseline;

  /** Inline error for a field key, with the test id the specs rely on. */
  const err = (key: string) => ({
    error: fieldErrors[key] ?? null,
    errorTestId: `field-error-${key}`,
  });

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
    <main className="settings-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title={`${bot.name} — settings`}
        purpose="Configure your assistant, appearance and website access. Save settings applies appearance changes live."
      />
      <p>
        Organization:{" "}
        {staffOrganizations?.find((org) => org.id === tenantId)?.name ??
          "Current organization"}{" "}
        (read-only)
      </p>
      <Card className="status-card" data-status={bot.status}>
        <div className="status-row">
          <span>
            Status: <LabelBadge value={bot.status} />
          </span>
          {canEdit && bot.status !== "archived" && (
            <div className="status-actions">
              {bot.status !== "active" && (
                <Button
                  type="button"
                  data-testid="activate-bot"
                  disabled={transitioning}
                  onClick={() => void transitionTo("active")}
                >
                  {transitioning ? "Activating…" : "Activate bot"}
                </Button>
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
        {bot.status === "draft" && (
          <p className="muted">
            This bot is a draft: it was created but has not been activated, so
            it is not answering visitors yet. Work through the launch readiness
            list below, then press Activate bot.
          </p>
        )}
        {bot.status === "paused" && (
          <p className="muted">
            This bot is paused and is not answering visitors until it is
            activated again.
          </p>
        )}
      </Card>
      {canEdit && (
        <BotReadinessCard
          tenantId={tenantId}
          botId={botId}
          refreshKey={readinessKey}
        />
      )}
      {bot.widget_locator && (
        <p className="muted">
          Widget locator:{" "}
          <code data-testid="settings-locator">{bot.widget_locator}</code>
        </p>
      )}
      {!canEdit && (
        <Notice message="Only platform operators can edit bot settings." />
      )}
      <form
        className="settings-form"
        onSubmit={onSave}
        onChange={() => setSaved(false)}
      >
        <FormSection
          title="Identity"
          description="How the assistant introduces itself and the business it speaks for."
        >
          <Field label="Assistant name" {...err("assistant_name")}>
            {(control) => (
              <input
                {...control}
                name="assistant_name"
                disabled={!canEdit}
                required
                maxLength={100}
                value={assistantName}
                onChange={(event) => setAssistantName(event.target.value)}
              />
            )}
          </Field>
          <Field
            label="Business name"
            hint="Defaults to the organization name; edit it if customers know the business by another name."
            {...err("business_name")}
          >
            {(control) => (
              <input
                {...control}
                name="business_name"
                disabled={!canEdit}
                maxLength={100}
                value={businessName}
                onChange={(event) => setBusinessNameEdit(event.target.value)}
              />
            )}
          </Field>
          <Field label="Business description" {...err("business_description")}>
            {(control) => (
              <textarea
                {...control}
                dir="auto"
                name="business_description"
                disabled={!canEdit}
                rows={3}
                maxLength={1000}
                value={businessDescription}
                onChange={(event) => setBusinessDescription(event.target.value)}
              />
            )}
          </Field>
          <Field label="Default language" {...err("default_language")}>
            {(control) => (
              <select
                {...control}
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
            )}
          </Field>
        </FormSection>

        <FormSection
          title="Appearance"
          description="Colour, avatar, position and the widget theme, with a live preview."
          data-testid="settings-appearance"
        >
          <div className="field-grid">
            <Field label="Widget colour (hex, e.g. #1a2b3c)" {...err("colour")}>
              {(control) => (
                <input
                  {...control}
                  name="colour"
                  disabled={!canEdit}
                  value={colour}
                  onChange={(event) => setColour(event.target.value)}
                />
              )}
            </Field>
            <Field label="Widget position" {...err("position")}>
              {(control) => (
                <select
                  {...control}
                  name="position"
                  disabled={!canEdit}
                  value={position}
                  onChange={(event) =>
                    setPosition(event.target.value as "left" | "right")
                  }
                >
                  <option value="left">Left</option>
                  <option value="right">Right</option>
                </select>
              )}
            </Field>
          </div>
          <Field
            label="Widget avatar (public http(s) image URL)"
            {...err("avatar")}
          >
            {(control) => (
              <input
                {...control}
                name="avatar"
                disabled={!canEdit}
                value={avatar}
                onChange={(event) => setAvatar(event.target.value)}
              />
            )}
          </Field>
          <section
            aria-label="Widget appearance"
            className="theme-appearance"
            data-testid="widget-appearance"
          >
            <div>
              <h3>Widget appearance</h3>
              <p className="muted">
                Pick a preset, then adjust any colour. The preview shows the
                widget exactly as visitors will see it; Save settings applies
                it.
              </p>
              <WidgetThemeEditor
                draft={themeDraft}
                brand={colour}
                disabled={!canEdit}
                onChange={(next) => {
                  setThemeDraft(next);
                  setThemeActive(true);
                  setSaved(false);
                }}
              />
              {fieldErrors["theme"] && (
                <p
                  role="alert"
                  className="field-error"
                  data-testid="field-error-theme"
                >
                  {fieldErrors["theme"]}
                </p>
              )}
            </div>
            <WidgetPreview
              theme={{ preset: themeDraft.preset, ...themeDraft.slots }}
              colour={colour}
              lang={defaultLanguage}
              name={assistantName || bot.name}
              welcome={defaultLanguage === "ar" ? welcomeAr : welcomeEn}
            />
          </section>
        </FormSection>

        <FormSection
          title="Messages"
          description="What visitors see when the widget opens."
        >
          <Field
            id="field-welcome_en"
            label="Welcome message (EN)"
            {...err("welcome_message.en")}
          >
            {(control) => (
              <input
                {...control}
                name="welcome_en"
                disabled={!canEdit}
                maxLength={500}
                value={welcomeEn}
                onChange={(event) => setWelcomeEn(event.target.value)}
              />
            )}
          </Field>
          <Field label="Welcome message (AR)" {...err("welcome_message.ar")}>
            {(control) => (
              <input
                {...control}
                name="welcome_ar"
                dir="auto"
                disabled={!canEdit}
                maxLength={500}
                value={welcomeAr}
                onChange={(event) => setWelcomeAr(event.target.value)}
              />
            )}
          </Field>
          <Field
            label="Opening questions (one per line, max 10)"
            {...err("opening_questions")}
          >
            {(control) => (
              <textarea
                {...control}
                dir="auto"
                name="opening_questions"
                disabled={!canEdit}
                rows={4}
                value={openingQuestions}
                onChange={(event) => setOpeningQuestions(event.target.value)}
              />
            )}
          </Field>
        </FormSection>

        <FormSection
          title="Contact & handoff"
          description="Where customers are sent when the assistant cannot help."
        >
          <div className="field-grid">
            <Field
              id="field-support_email"
              label="Support email"
              {...err("support_email")}
            >
              {(control) => (
                <input
                  {...control}
                  name="support_email"
                  type="email"
                  disabled={!canEdit}
                  value={supportEmail}
                  onChange={(event) => setSupportEmail(event.target.value)}
                />
              )}
            </Field>
            <Field label="Support phone" {...err("support_phone")}>
              {(control) => (
                <input
                  {...control}
                  name="support_phone"
                  disabled={!canEdit}
                  maxLength={30}
                  value={supportPhone}
                  onChange={(event) => setSupportPhone(event.target.value)}
                />
              )}
            </Field>
          </div>
          <div className="field">
            <label className="check-control">
              Human handoff enabled
              <input
                name="handoff_enabled"
                type="checkbox"
                disabled={!canEdit}
                checked={handoffEnabled}
                onChange={(event) => setHandoffEnabled(event.target.checked)}
              />
            </label>
            {fieldErrors["handoff_enabled"] && (
              <p
                role="alert"
                className="field-error"
                data-testid="field-error-handoff_enabled"
              >
                {fieldErrors["handoff_enabled"]}
              </p>
            )}
          </div>
        </FormSection>

        <FormSection
          title="Access"
          description="Which websites may show this widget."
        >
          <Field
            id="field-allowed_domains"
            label="Allowed domains (one per line, max 50)"
            hint="Paste hostnames or full URLs; they are reduced to bare hostnames on save. Leave empty to allow any site."
            {...err("allowed_domains")}
          >
            {(control) => (
              <textarea
                {...control}
                dir="auto"
                name="allowed_domains"
                disabled={!canEdit}
                rows={3}
                value={allowedDomains}
                onChange={(event) => setAllowedDomains(event.target.value)}
              />
            )}
          </Field>
        </FormSection>

        {canEdit && (
          <FormSection
            title="AI"
            description="Tone and rules are saved with the form. The AI tier below saves instantly on its own."
          >
            <BotToneField
              value={toneAndRules}
              onChange={setToneAndRules}
              disabled={!canEdit}
              error={fieldErrors["tone_and_rules"] ?? null}
            />
          </FormSection>
        )}
        {saveError && <Notice message={saveError} tone="error" />}
        {saved && <Notice message="Settings saved." />}
        {canEdit && (
          <div className="settings-savebar" data-testid="settings-savebar">
            <span className="save-state" data-dirty={dirty ? "true" : "false"}>
              {saving
                ? "Saving form changes…"
                : dirty
                  ? "Unsaved form changes"
                  : "Form is up to date"}
            </span>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        )}
      </form>
      {canEdit && (
        <div id="settings-ai-tier" className="tier-block">
          <p className="muted tier-note">
            <strong>Saves instantly:</strong> changing the AI tier below does
            not need the Save settings button.
          </p>
          <RagTierControl tenantId={tenantId} botId={botId} />
        </div>
      )}
      {bot.status === "archived" && <Notice message="This bot is archived." />}
    </main>
  );
}
