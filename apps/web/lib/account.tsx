"use client";

/**
 * Shared change-password form (S4), used by the /account page in both the
 * client workspace shell and the platform admin shell. The new password
 * follows the same minimum length as registration; every failure shows a
 * safe, actionable message (no account details, no internals).
 */

import { useState } from "react";

import * as api from "./api";
import { PasswordField } from "./password-field";
import { useSession } from "./session";

const MIN_PASSWORD_LENGTH = 8;

export function AccountForm() {
  const { me } = useSession();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setChanged(false);
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("The new password must differ from the current password.");
      return;
    }
    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      // Success: this session was rotated server-side, every other session
      // of the user is signed out.
      setChanged(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not change the password.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section aria-label="Change password">
      <h2>Change password</h2>
      <form onSubmit={onSubmit}>
        <div className="password-control">
          <label htmlFor="account-current-password">Current password</label>
          <PasswordField
            id="account-current-password"
            name="current-password"
            autoComplete="current-password"
            required
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </div>
        <div className="password-control">
          <label htmlFor="account-new-password">New password</label>
          <PasswordField
            id="account-new-password"
            name="new-password"
            autoComplete="new-password"
            required
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </div>
        <div className="password-control">
          <label htmlFor="account-confirm-password">Confirm new password</label>
          <PasswordField
            id="account-confirm-password"
            name="confirm-password"
            autoComplete="new-password"
            required
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </div>
        {error && (
          <p role="alert" data-testid="account-error">
            {error}
          </p>
        )}
        {changed && (
          <p role="status" data-testid="account-success">
            Password changed. Your other signed-in sessions were signed out.
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Change password"}
        </button>
      </form>
      <p className="muted">Signed in as {me?.email ?? "…"}</p>
    </section>
  );
}
