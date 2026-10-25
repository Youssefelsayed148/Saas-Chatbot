"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { PasswordField } from "@/lib/password-field";
import { ThemeToggle } from "@/lib/theme";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import { Icon } from "@/lib/icons";
import { Button, Field, Notice } from "@/lib/ui";
import "@/app/auth-screen.css";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const next = searchParams.get("next") ?? "";

  // The session-expired redirect lands here with the original path preserved.
  const destination =
    next.startsWith("/") && !next.startsWith("//") ? next : "/app";

  useEffect(() => {
    void api.me().then((existing) => {
      if (existing) router.replace("/app");
    });
  }, [router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const missingEmail = email.trim() ? null : "Enter your email address.";
    const missingPassword = password ? null : "Enter your password.";
    setEmailError(missingEmail);
    setPasswordError(missingPassword);
    if (missingEmail || missingPassword) return;
    setSubmitting(true);
    try {
      await api.login(email, password);
      await refresh(); // update the session context before navigating
      router.push(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-split">
      <aside className="auth-panel">
        <span className="brand-mark" aria-hidden="true">
          <Icon name="sparkle" size={22} />
        </span>
        <p className="auth-panel-name">Website Chatbot</p>
        <p className="auth-panel-copy">
          Answer visitors instantly, hand off to your team when it matters.
        </p>
      </aside>
      <div className="auth-page">
        <div className="auth-brand">
          <ThemeToggle />
        </div>
        <h1>Sign in</h1>
        <p className="page-purpose">
          Welcome back. Continue helping your visitors.
        </p>
        <form onSubmit={onSubmit} noValidate>
          <Field label="Email" error={emailError}>
            {(control) => (
              <input
                {...control}
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            )}
          </Field>
          <Field label="Password" error={passwordError}>
            {(control) => (
              <PasswordField
                {...control}
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            )}
          </Field>
          {error && <Notice message={error} tone="error" scope="item" />}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="auth-footer">
          Forgot your password? Contact your administrator.
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="eyebrow">Loading…</main>}>
      <LoginForm />
    </Suspense>
  );
}
