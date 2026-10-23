"use client";

import Link from "next/link";
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
  const [submitting, setSubmitting] = useState(false);
  // Registration is closed by default: the self-serve signup flag comes from
  // /auth/config, as on /register. While unknown or on fetch failure the link
  // stays hidden (fail closed).
  const [selfServeSignup, setSelfServeSignup] = useState(false);
  const next = searchParams.get("next") ?? "";

  // The session-expired redirect lands here with the original path preserved.
  const destination =
    next.startsWith("/") && !next.startsWith("//") ? next : "/app";

  useEffect(() => {
    void api
      .authConfig()
      .then((features) => setSelfServeSignup(features.self_serve_signup))
      .catch(() => setSelfServeSignup(false));
    void api.me().then((existing) => {
      if (existing) router.replace("/app");
    });
  }, [router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
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
    <main className="auth-page">
      <div className="auth-brand">
        <span className="brand-mark" aria-hidden="true">
          <Icon name="sparkle" size={22} />
        </span>
        <span>Website Chatbot SaaS</span>
        <ThemeToggle />
      </div>
      <p className="eyebrow">YOUR AI WORKSPACE</p>
      <h1>Sign in</h1>
      <p className="page-purpose">
        Welcome back. Continue helping your visitors.
      </p>
      <form onSubmit={onSubmit}>
        <Field label="Email">
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
        <Field label="Password">
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
      {selfServeSignup && (
        <p className="auth-footer">
          No account yet? <Link href="/register">Register</Link>
        </p>
      )}
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
