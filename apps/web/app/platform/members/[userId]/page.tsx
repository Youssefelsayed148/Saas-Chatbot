"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { MembershipControls, PasswordPanel } from "@/lib/staff-members";
import { ConfirmAction, Loading, Notice } from "@/lib/ui";

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
    <main>
      {error && <Notice tone="error" message={error} />}
      {user ? (
        <>
          <h1>{user.email}</h1>
          <p>{user.phone}</p>
          <p>{user.is_active ? "Active" : "Inactive"}</p>
          <MembershipControls user={user} refresh={load} />
          <section aria-label="Reset password">
            <h2>Reset password</h2>
            <form
              onSubmit={(e) => {
                void reset(e);
              }}
            >
              <label>
                New password
                <input
                  type="password"
                  autoComplete="new-password"
                  required={!generate}
                  disabled={generate}
                  minLength={8}
                  maxLength={200}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <button
                type="button"
                aria-pressed={generate}
                onClick={() => {
                  setGenerate(!generate);
                  setPassword("");
                }}
              >
                {generate ? "Use typed password" : "Generate password"}
              </button>
              <button disabled={busy}>Reset password</button>
            </form>
          </section>
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
