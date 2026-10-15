"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { PasswordField } from "@/lib/password-field";
import { ThemeToggle } from "@/lib/theme";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";

const MIN_PASSWORD_LENGTH = 8;

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [clientName, setClientName] = useState("");
  const [botName, setBotName] = useState("Website assistant");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const next = searchParams.get("next") ?? "";
  const destination =
    next.startsWith("/") && !next.startsWith("//") ? next : "/app";
  const isInviteSignup = destination.startsWith("/accept-invite");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setSubmitting(true);
    try {
      try {
        await api.register(email, password);
      } catch (caught) {
        if (
          !(caught instanceof api.ApiError) ||
          caught.code !== "EMAIL_TAKEN"
        ) {
          throw caught;
        }
        // Recover a signup whose account commit succeeded before its
        // provisioning response reached the browser.
        await api.login(email, password);
      }
      await refresh(); // update the session context before navigating
      if (isInviteSignup) {
        router.push(destination);
      } else {
        const signup = await api.selfServiceSignup(clientName, botName);
        // Provisioning just created the membership: reload the session so
        // role-gated pages (e.g. knowledge uploads) see the new tenant.
        await refresh();
        router.push(`/app/${signup.result.tenant_id}/bots`);
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Registration failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-brand">
        <span className="brand-mark" aria-hidden="true">
          ✧
        </span>
        <span>Website Chatbot SaaS</span>
        <ThemeToggle />
      </div>
      <p className="eyebrow">YOUR AI WORKSPACE</p>
      <h1>Register</h1>
      <p className="page-purpose">
        Create your workspace and first website assistant.
      </p>
      <form onSubmit={onSubmit}>
        {!isInviteSignup && (
          <>
            <label>
              Organization name
              <input
                name="client-name"
                required
                maxLength={200}
                value={clientName}
                onChange={(event) => setClientName(event.target.value)}
              />
            </label>
            <label>
              First bot name
              <input
                name="bot-name"
                required
                maxLength={100}
                value={botName}
                onChange={(event) => setBotName(event.target.value)}
              />
            </label>
          </>
        )}
        <label>
          Email
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <div className="password-control">
          <label htmlFor="auth-password">Password</label>
          <PasswordField
            id="auth-password"
            type="password"
            name="new-password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p>
        Already registered? <Link href="/login">Sign in</Link>
      </p>
    </main>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<main className="eyebrow">Loading…</main>}>
      <RegisterForm />
    </Suspense>
  );
}
