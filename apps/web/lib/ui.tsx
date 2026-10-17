"use client";
import { useRef, type ReactNode } from "react";
export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <span>{label}</span>
      <div aria-hidden="true" className="skeleton" />
      <div aria-hidden="true" className="skeleton short" />
    </div>
  );
}
export function Notice({
  message,
  tone = "info",
  onRetry,
}: {
  message: string;
  tone?: "info" | "error";
  onRetry?: () => void;
}) {
  return (
    <div
      className={`notice ${tone === "info" && /saved|copied|created|updated/i.test(message) ? "success-toast" : ""}`}
      data-tone={tone}
    >
      <p role={tone === "error" ? "alert" : "status"}>{message}</p>
      {tone === "error" && (
        <button
          type="button"
          className="quiet-button"
          onClick={onRetry ?? (() => window.location.reload())}
        >
          Retry page
        </button>
      )}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-symbol" aria-hidden="true">
        ✧
      </span>
      <p className="muted">{children}</p>
    </div>
  );
}
export function ConfirmAction({
  children,
  title,
  description,
  onConfirm,
  disabled,
  confirmLabel = "Confirm",
  testId,
}: {
  children: ReactNode;
  title: string;
  description: string;
  onConfirm: () => void;
  disabled?: boolean;
  confirmLabel?: string;
  testId?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button
        type="button"
        data-testid={testId}
        disabled={disabled}
        className="danger-button"
        onClick={() => dialog.current?.showModal()}
      >
        {children}
      </button>
      <dialog ref={dialog} aria-label={title}>
        <h2>{title}</h2>
        <p>{description}</p>
        <div className="action-row">
          <button
            type="button"
            autoFocus
            className="quiet-button"
            onClick={() => dialog.current?.close()}
          >
            Cancel
          </button>
          <button
            type="button"
            className="danger-button"
            disabled={disabled}
            onClick={() => {
              dialog.current?.close();
              onConfirm();
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </dialog>
    </>
  );
}
