"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { MembershipControls, PasswordPanel } from "@/lib/staff-members";
import {
  Button,
  ConfirmAction,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import "@/app/staff-screens.css";

export default function MemberPage() {
  const { userId } = useParams<{ userId: string }>();
  const [user, setUser] = useState<api.StaffUser | null>(null);
  const [password, setPassword] = useState("");
  const [generate, setGenerate] = useState(false);
  const [issued, setIssued] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setUser(await api.platformUser(userId));
  }, [userId]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load().catch(() => setError("Could not load user."));
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);
  async function active() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      setUser(await api.platformUserActive(userId, !user.is_active));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Account update failed.");
    } finally {
      setBusy(false);
    }
  }
  async function reset(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setIssued("");
    try {
      const result = await api.platformResetPassword(
        userId,
        generate ? { generate: true } : { password },
      );
      setIssued(result.generated_password ?? password);
      setPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Password reset failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="staff-page">
      {error && <Notice tone="error" message={error} />}
      {user ? (
        <>
          <PageHeader
            title={<bdi dir="ltr">{user.email}</bdi>}
            purpose={user.phone ? <bdi dir="ltr">{user.phone}</bdi> : undefined}
            actions={
              <StatusBadge
                value={user.is_active ? "active" : "inactive"}
                tone={user.is_active ? "success" : "neutral"}
              >
                {user.is_active ? "Active" : "Inactive"}
              </StatusBadge>
            }
          />
          <MembershipControls user={user} refresh={load} />
          <section aria-label="Reset password" className="form-section">
            <header>
              <h2>Reset password</h2>
            </header>
            <form
              onSubmit={(e) => {
                void reset(e);
              }}
            >
              <Field label="New password">
                {(control) => (
                  <input
                    {...control}
                    type="password"
                    autoComplete="new-password"
                    required={!generate}
                    disabled={generate}
                    minLength={8}
                    maxLength={200}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>
              <Button
                type="button"
                variant="quiet"
                aria-pressed={generate}
                onClick={() => {
                  setGenerate(!generate);
                  setPassword("");
                }}
              >
                {generate ? "Use typed password" : "Generate password"}
              </Button>
              <Button type="submit" disabled={busy}>
                Reset password
              </Button>
            </form>
          </section>
          <section aria-label="Account status" className="form-section">
            <header>
              <h2>Account status</h2>
              <p>
                {user.is_active
                  ? "Deactivating signs the user out everywhere."
                  : "This account is inactive and cannot sign in."}
              </p>
            </header>
            <div className="action-row">
              <ConfirmAction
                title={user.is_active ? "Deactivate user" : "Reactivate user"}
                description={
                  user.is_active
                    ? "This user will be signed out of every session and unable to log in."
                    : "Allow this user to log in again?"
                }
                disabled={busy}
                onConfirm={() => {
                  void active();
                }}
              >
                {user.is_active ? "Deactivate user" : "Reactivate user"}
              </ConfirmAction>
            </div>
          </section>
          {issued && (
            <PasswordPanel password={issued} onDismiss={() => setIssued("")} />
          )}
        </>
      ) : (
        <Loading />
      )}
    </main>
  );
}
