"use client";
import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Icon } from "./icons";

function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

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
  retryLabel = "Retry page",
  scope = "page",
}: {
  message: string;
  tone?: "info" | "error";
  onRetry?: () => void;
  /** Honest name for the action: a page reload unless onRetry says otherwise. */
  retryLabel?: string;
  /** "item" marks an error about one row or action (a failed job, a failed
   * save): it names the problem but offers no page-level retry. */
  scope?: "page" | "item";
}) {
  return (
    <div
      className={`notice ${tone === "info" && /saved|copied|created|updated/i.test(message) ? "success-toast" : ""}`}
      data-tone={tone}
    >
      <p role={tone === "error" ? "alert" : "status"}>{message}</p>
      {tone === "error" && scope === "page" && (
        <button
          type="button"
          className="quiet-button"
          onClick={onRetry ?? (() => window.location.reload())}
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-symbol" aria-hidden="true">
        <Icon name="sparkle" size={22} />
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

/* ---- Shared components (D.4). Each forwards data-testid, aria-* and
 * className to its root element through the rest props. ---- */

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "quiet" | "danger";
}) {
  return (
    <button
      type={type}
      className={cx(
        variant === "quiet" && "quiet-button",
        variant === "danger" && "danger-button",
        className,
      )}
      {...rest}
    />
  );
}

type FieldControlProps = {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  "aria-required"?: true;
};

/** Label above the control, hint below, error inline (announced as an alert).
 * The render function receives the id and aria wiring for the control. */
export function Field({
  label,
  hint,
  error,
  errorTestId,
  required,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** data-testid for the inline error element (existing specs key on it). */
  errorTestId?: string;
  required?: boolean;
  children: (control: FieldControlProps) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy =
    [hint ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div
      className={cx("field", className)}
      data-invalid={error ? "true" : undefined}
      {...rest}
    >
      <label htmlFor={id}>
        {label}
        {required && (
          <span className="field-required" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children({
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        "aria-required": required ? true : undefined,
      })}
      {hint && (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          className="field-error"
          role="alert"
          data-testid={errorTestId}
        >
          {error}
        </p>
      )}
    </div>
  );
}

export function FormSection({
  title,
  description,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title: ReactNode;
  description?: ReactNode;
}) {
  const id = useId();
  return (
    <section
      className={cx("form-section", className)}
      aria-labelledby={id}
      {...rest}
    >
      <header>
        <h2 id={id}>{title}</h2>
        {description && <p>{description}</p>}
      </header>
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  eyebrow,
  purpose,
  actions,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title: ReactNode;
  eyebrow?: ReactNode;
  purpose?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={cx("page-header", className)} {...rest}>
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {purpose && <p className="page-purpose">{purpose}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  actions,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={cx("ui-card", className)} {...rest}>
      {(title || actions) && (
        <header className="section-heading">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";
const TONES: Record<string, StatusTone> = {
  active: "success",
  published: "success",
  succeeded: "success",
  resolved: "success",
  ready: "success",
  failed: "danger",
  archived: "danger",
  error: "danger",
  paused: "warning",
  pending: "warning",
  running: "warning",
  waiting_human: "warning",
  draft: "info",
};
export function StatusBadge({
  value,
  tone,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  value: string;
  tone?: StatusTone;
  children?: ReactNode;
}) {
  return (
    <span
      className={cx("status-badge", className)}
      data-value={value}
      data-tone={tone ?? TONES[value] ?? "neutral"}
      {...rest}
    >
      {children ?? value.replace(/_/g, " ")}
    </span>
  );
}

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  className?: string;
};
/** Table that scrolls horizontally inside its own keyboard-focusable region
 * and never breaks words mid-word. */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  caption,
  empty,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  caption: string;
  empty?: ReactNode;
}) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    <div
      className={cx("table-scroll", className)}
      role="region"
      aria-label={caption}
      tabIndex={0}
      {...rest}
    >
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={c.className}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td key={c.key} className={c.className}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type TabItem = { id: string; label: ReactNode; testId?: string };
/** Tab list with roving focus: Arrow keys (direction-aware), Home and End move
 * and select; only the selected tab is in the tab order. Render the panel
 * with TabPanel using the same idPrefix. */
export function Tabs({
  tabs,
  value,
  onChange,
  idPrefix,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "onChange"> & {
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  idPrefix: string;
}) {
  const list = useRef<HTMLDivElement>(null);
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const next = rtl ? "ArrowLeft" : "ArrowRight";
    const prev = rtl ? "ArrowRight" : "ArrowLeft";
    const index = tabs.findIndex((t) => t.id === value);
    let target = -1;
    if (event.key === next) target = (index + 1) % tabs.length;
    else if (event.key === prev)
      target = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = tabs.length - 1;
    if (target < 0) return;
    event.preventDefault();
    onChange(tabs[target].id);
    list.current
      ?.querySelectorAll<HTMLElement>('[role="tab"]')
      [target]?.focus();
  }
  return (
    <div
      ref={list}
      role="tablist"
      className={cx("ui-tabs", className)}
      onKeyDown={onKeyDown}
      {...rest}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${tab.id}`}
          aria-selected={tab.id === value}
          aria-controls={`${idPrefix}-panel-${tab.id}`}
          tabIndex={tab.id === value ? 0 : -1}
          data-testid={tab.testId}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
export function TabPanel({
  idPrefix,
  tabId,
  active,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & {
  idPrefix: string;
  tabId: string;
  active: boolean;
}) {
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${tabId}`}
      aria-labelledby={`${idPrefix}-tab-${tabId}`}
      hidden={!active}
      tabIndex={0}
      {...rest}
    >
      {active && children}
    </div>
  );
}

/** Controlled modal on the native <dialog>: focus moves in on open and returns
 * to the opener on close; Escape and a click on the backdrop call onClose. */
export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDialogElement>, "title" | "onClose"> & {
  open: boolean;
  onClose: () => void;
  title: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      opener.current = document.activeElement as HTMLElement | null;
      dialog.showModal();
    } else if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={cx("ui-dialog", className)}
      aria-labelledby={titleId}
      onClose={() => {
        opener.current?.focus();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      {...rest}
    >
      <div className="dialog-heading">
        <h2 id={titleId}>{title}</h2>
        <button
          type="button"
          className="quiet-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      {open && children}
    </dialog>
  );
}

/** Transient message. Does not take focus; announced politely (errors as an
 * alert). Dismiss with the button or Escape; the timer pauses while hovered or
 * focused. Errors stay until dismissed. */
export function Toast({
  message,
  tone = "info",
  onDismiss,
  timeoutMs = 6000,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  message: string;
  tone?: "info" | "error";
  onDismiss: () => void;
  timeoutMs?: number;
}) {
  const paused = useRef(false);
  useEffect(() => {
    if (tone === "error" || !timeoutMs) return;
    let left = timeoutMs;
    const timer = window.setInterval(() => {
      if (paused.current) return;
      left -= 250;
      if (left <= 0) onDismiss();
    }, 250);
    return () => window.clearInterval(timer);
  }, [tone, timeoutMs, onDismiss]);
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDismiss]);
  return (
    <div className="toast-region">
      <div
        className={cx("notice", className)}
        data-tone={tone}
        role={tone === "error" ? "alert" : "status"}
        onMouseEnter={() => (paused.current = true)}
        onMouseLeave={() => (paused.current = false)}
        onFocus={() => (paused.current = true)}
        onBlur={() => (paused.current = false)}
        {...rest}
      >
        <p>{message}</p>
        <button
          type="button"
          className="quiet-button"
          aria-label="Dismiss message"
          onClick={onDismiss}
        >
          <Icon name="close" />
        </button>
      </div>
    </div>
  );
}
