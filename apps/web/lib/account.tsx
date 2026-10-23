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
import { Button, Field, FormSection } from "./ui";

const MIN_PASSWORD_LENGTH = 8;

export function AccountForm() {
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
    <FormSection
      title="Change password"
      description="Changing it signs out your other sessions."
    >
      <form onSubmit={onSubmit}>
        <Field label="Current password">
          {(control) => (
            <PasswordField
              {...control}
              name="current-password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          )}
        </Field>
        <Field label="New password">
          {(control) => (
            <PasswordField
              {...control}
              name="new-password"
              autoComplete="new-password"
              required
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          )}
        </Field>
        <Field label="Confirm new password">
          {(control) => (
            <PasswordField
              {...control}
              name="confirm-password"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          )}
        </Field>
        {error && (
          <p
            role="alert"
            className="auth-message"
            data-tone="error"
            data-testid="account-error"
          >
            {error}
          </p>
        )}
        {changed && (
          <p
            role="status"
            className="auth-message"
            data-tone="success"
            data-testid="account-success"
          >
            Password changed. Your other signed-in sessions were signed out.
          </p>
        )}
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Change password"}
        </Button>
      </form>
    </FormSection>
  );
}
