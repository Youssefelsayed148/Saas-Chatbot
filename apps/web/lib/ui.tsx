"use client";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import Link from "next/link";
import { Icon, type IconName } from "./icons";

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

/* ---- B2 primitives (UI polish). Styles live in globals.css under
 * "UI polish primitives". LinkButton: landing, bots, org list, readiness.
 * StatCard + Meter: dashboards. Switch, ColorField, LimitField, SectionNav,
 * StickyActionBar, StatusPill: settings forms and readiness (B6). ---- */

export type LinkButtonVariant =
  "primary" | "secondary" | "ghost" | "danger" | "icon";

/** A link that looks like a button. Renders a next/link <a> for internal paths
 * and a plain <a> for anchors, API downloads and external URLs, so role=link,
 * href and aria-label are kept. Never an underlined text link. */
export function LinkButton({
  href,
  variant = "secondary",
  size = "md",
  icon,
  iconEnd,
  external,
  className,
  children,
  ...rest
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  variant?: LinkButtonVariant;
  size?: "sm" | "md";
  icon?: IconName;
  iconEnd?: IconName;
  external?: boolean;
}) {
  const iconSize = size === "sm" ? 14 : 16;
  const body = (
    <>
      {icon && <Icon name={icon} size={iconSize} />}
      {children != null && <span>{children}</span>}
      {iconEnd && <Icon name={iconEnd} size={iconSize} />}
    </>
  );
  const props = {
    className: cx("link-button", className),
    "data-variant": variant,
    "data-size": size,
    ...rest,
  };
  const plain =
    external ||
    !href.startsWith("/") ||
    href.startsWith("/api/") ||
    href.includes("#");
  if (plain) {
    return (
      <a
        href={href}
        {...props}
        {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      >
        {body}
      </a>
    );
  }
  return (
    <Link href={href} {...props}>
      {body}
    </Link>
  );
}

export type StatDelta = {
  /** Already formatted, e.g. "+12%" or "-3". */
  value: string;
  direction: "up" | "down" | "flat";
  /** Whether "up" is good; default true. An arrow accompanies the colour. */
  upIsGood?: boolean;
  /** e.g. "vs previous 30 days" (read by screen readers). */
  label?: string;
};
/** KPI tile. The label never ends in a colon; hint renders only when given. */
export function StatCard({
  label,
  value,
  delta,
  spark,
  hint,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  label: ReactNode;
  value: ReactNode;
  delta?: StatDelta;
  /** Slot for a small trend chart. */
  spark?: ReactNode;
  hint?: ReactNode;
}) {
  const text =
    typeof label === "string" ? label.replace(/\s*:\s*$/, "") : label;
  const quality = delta
    ? delta.direction === "flat"
      ? "flat"
      : (delta.direction === "up") === (delta.upIsGood ?? true)
        ? "good"
        : "bad"
    : undefined;
  return (
    <div className={cx("stat-card", className)} {...rest}>
      <span>{text}</span>
      <strong>{value}</strong>
      {delta && (
        <span className="stat-delta" data-tone={quality}>
          <Icon
            name={delta.direction === "flat" ? "minus" : "arrow-right"}
            size={12}
            className={`stat-delta-${delta.direction}`}
          />
          {delta.value}
          {delta.label && <span className="sr-only"> {delta.label}</span>}
        </span>
      )}
      {spark && <div className="stat-spark">{spark}</div>}
      {hint && <small>{hint}</small>}
    </div>
  );
}

/** used/limit bar. Danger at or over the limit, warning from 80%. Exposed as
 * role="meter" with a text alternative; limit null = uncapped. */
export function Meter({
  used,
  limit,
  label,
  unit,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  used: number;
  limit: number | null;
  label: string;
  unit?: string;
}) {
  const capped = limit != null && limit > 0;
  const ratio = capped ? used / limit : 0;
  const tone = !capped
    ? "none"
    : ratio >= 1
      ? "danger"
      : ratio >= 0.8
        ? "warning"
        : "ok";
  const fmt = (n: number) => n.toLocaleString("en-US");
  const suffix = unit ? ` ${unit}` : "";
  const text = capped
    ? `${fmt(used)} of ${fmt(limit)}${suffix}${ratio >= 1 ? " (limit reached)" : ""}`
    : `${fmt(used)}${suffix} (uncapped)`;
  return (
    <div className={cx("ui-meter", className)} data-tone={tone} {...rest}>
      <div
        className="ui-meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={capped ? limit : Math.max(used, 1)}
        aria-valuenow={capped ? Math.min(used, limit) : used}
        aria-valuetext={text}
      >
        <div
          className="ui-meter-fill"
          style={{ inlineSize: `${capped ? Math.min(100, ratio * 100) : 0}%` }}
        />
      </div>
      <span className="ui-meter-text">{text}</span>
    </div>
  );
}

/** On/off control: a native checkbox with role="switch" (keyboard and form safe). */
export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLLabelElement>, "onChange"> & {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <label className={cx("ui-switch", className)} htmlFor={id} {...rest}>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="ui-switch-track" aria-hidden="true">
        <span className="ui-switch-thumb" />
      </span>
      <span className="ui-switch-text">
        {label}
        {hint && (
          <small id={`${id}-hint`} className="field-hint">
            {hint}
          </small>
        )}
      </span>
    </label>
  );
}

const HEX = /^#[0-9a-fA-F]{6}$/;
function luminance(hex: string) {
  const c = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
/** WCAG contrast ratio of two #rrggbb colours. */
export function contrastRatio(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
/** Colour picker + hex box + contrast result against `against` (the colour of
 * text placed on it; default white). Reports only valid #rrggbb values. */
export function ColorField({
  label,
  value,
  onChange,
  against = "#ffffff",
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "onChange"> & {
  label: string;
  value: string;
  onChange: (hex: string) => void;
  against?: string;
}) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [prev, setPrev] = useState(value);
  if (prev !== value) {
    setPrev(value);
    setDraft(value);
  }
  const valid = HEX.test(draft);
  const ratio = valid ? contrastRatio(draft, against) : 0;
  return (
    <div className={cx("ui-color-field", className)} {...rest}>
      <label htmlFor={`${id}-hex`}>{label}</label>
      <div className="ui-color-inputs">
        <input
          type="color"
          aria-label={`${label} picker`}
          value={valid ? draft.toLowerCase() : "#000000"}
          onChange={(event) => {
            setDraft(event.target.value);
            onChange(event.target.value);
          }}
        />
        <input
          id={`${id}-hex`}
          type="text"
          spellCheck={false}
          maxLength={7}
          value={draft}
          aria-invalid={valid ? undefined : true}
          aria-describedby={`${id}-msg`}
          onChange={(event) => {
            setDraft(event.target.value);
            if (HEX.test(event.target.value)) onChange(event.target.value);
          }}
        />
      </div>
      <p
        id={`${id}-msg`}
        className="field-hint"
        data-tone={!valid ? "danger" : ratio >= 4.5 ? "success" : "warning"}
        role={valid ? undefined : "alert"}
      >
        {!valid
          ? "Enter a colour as #rrggbb."
          : ratio >= 4.5
            ? `Contrast ${ratio.toFixed(1)}:1 with text. Passes.`
            : `Contrast ${ratio.toFixed(1)}:1 with text is too low (4.5:1 needed).`}
      </p>
    </div>
  );
}

/** Numeric limit with unit, stepper and an "Uncapped" placeholder (empty means
 * uncapped). Passing `used` adds a Meter. */
export function LimitField({
  label,
  unit,
  value,
  onChange,
  used,
  step = 1,
  min = 0,
  placeholder = "Uncapped",
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "onChange"> & {
  label: string;
  unit?: string;
  /** Empty string means uncapped. */
  value: string;
  onChange: (next: string) => void;
  used?: number;
  step?: number;
  min?: number;
  placeholder?: string;
}) {
  const id = useId();
  const num = value === "" ? null : Number(value);
  const limit = num != null && Number.isFinite(num) && num > 0 ? num : null;
  function bump(delta: number) {
    onChange(String(Math.max(min, (limit ?? 0) + delta)));
  }
  return (
    <div className={cx("ui-limit-field", className)} {...rest}>
      <label htmlFor={id}>{label}</label>
      <div className="ui-limit-control">
        <button
          type="button"
          className="quiet-button"
          aria-label={`Decrease ${label}`}
          onClick={() => bump(-step)}
        >
          <Icon name="minus" size={14} />
        </button>
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          step={step}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="quiet-button"
          aria-label={`Increase ${label}`}
          onClick={() => bump(step)}
        >
          <Icon name="plus" size={14} />
        </button>
        {unit && <span className="ui-limit-unit">{unit}</span>}
      </div>
      {used != null && (
        <Meter used={used} limit={limit} label={`${label} used`} unit={unit} />
      )}
    </div>
  );
}

export type SectionNavItem = { id: string; label: ReactNode };
/** In-page navigation to sections (anchors to element ids). `active` marks one
 * with aria-current; the page decides which. */
export function SectionNav({
  items,
  active,
  label = "Sections",
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "children"> & {
  items: SectionNavItem[];
  active?: string;
  label?: string;
}) {
  return (
    <nav
      className={cx("ui-section-nav", className)}
      aria-label={label}
      {...rest}
    >
      {items.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          aria-current={item.id === active ? "location" : undefined}
        >
          {item.label}
        </a>
      ))}
    </nav>
  );
}

/** Save bar pinned to the bottom of the viewport; renders nothing unless dirty. */
export function StickyActionBar({
  dirty,
  message = "You have unsaved changes",
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  dirty: boolean;
  message?: ReactNode;
  children: ReactNode;
}) {
  if (!dirty) return null;
  return (
    <div
      className={cx("ui-sticky-actions", className)}
      role="region"
      aria-label="Unsaved changes"
      {...rest}
    >
      <p>{message}</p>
      <div className="action-row">{children}</div>
    </div>
  );
}

/** Read-only state label, never a control: icon plus text (colour is not the
 * only signal), no hover or pointer styling. For readiness To do/Check/Done. */
export function StatusPill({
  tone = "neutral",
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  tone?: StatusTone;
  children: ReactNode;
}) {
  const icon: IconName =
    tone === "success"
      ? "check"
      : tone === "danger" || tone === "warning"
        ? "alert"
        : tone === "info"
          ? "info"
          : "dot";
  return (
    <span className={cx("status-pill", className)} data-tone={tone} {...rest}>
      <Icon name={icon} size={12} />
      {children}
    </span>
  );
}
