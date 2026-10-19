"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import * as api from "./api";
import { roleSatisfies, useSession } from "./session";
import { ThemeToggle } from "./theme";

type Destination = { label: string; href: string; symbol: React.ReactNode };
export function AppShell({
  tenantId,
  platform = false,
  children,
}: {
  tenantId?: string;
  platform?: boolean;
  children: ReactNode;
}) {
  const { me, refresh, roleIn, staffOrganizations, staffOrganizationsError } =
    useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const palette = useRef<HTMLDialogElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const membership = me?.memberships.find((m) => m.tenant_id === tenantId);
  const organizations = me?.is_platform_staff
    ? (staffOrganizations ?? []).map((org) => ({
        tenant_id: org.id,
        tenant_name: org.name,
      }))
    : (me?.memberships ?? []);
  const organizationName =
    organizations.find((org) => org.tenant_id === tenantId)?.tenant_name ??
    membership?.tenant_name;
  const role = tenantId ? roleIn(tenantId) : null;
  const base = `/app/${tenantId}`;
  const [conversationBot, setConversationBot] = useState<{
    tenant: string;
    id: string | null;
  } | null>(null);
  useEffect(() => {
    if (!tenantId || !me || platform || me.is_platform_staff) return;
    let cancelled = false;
    void api.listBots(tenantId, false).then(
      (bots) => {
        if (!cancelled)
          setConversationBot({ tenant: tenantId, id: bots[0]?.id ?? null });
      },
      () => {
        // The conversations landing page provides the retry/error state.
        if (!cancelled) setConversationBot({ tenant: tenantId, id: null });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [tenantId, me, platform]);
  const conversationsHref =
    conversationBot && conversationBot.tenant === tenantId && conversationBot.id
      ? `${base}/bots/${conversationBot.id}/conversations`
      : `${base}/conversations`;
  const links: Destination[] = platform
    ? [
        { label: "Clients", href: "/platform", symbol: "◈" },
        {
          label: "Change requests",
          href: "/platform/change-requests",
          symbol: <ChangeRequestIcon />,
        },
        { label: "Channels", href: "/platform/channels", symbol: "⇄" },
        { label: "Operations", href: "/platform/operations", symbol: "▥" },
        { label: "Client workspaces", href: "/app", symbol: "↗" },
      ]
    : tenantId
      ? [
          { label: "Overview", href: base, symbol: "◈" },
          ...(me?.is_platform_staff
            ? [{ label: "Bots", href: `${base}/bots`, symbol: "✧" }]
            : [
                {
                  label: "Conversations",
                  href: conversationsHref,
                  symbol: "▤",
                },
              ]),
          { label: "Inbox", href: `${base}/inbox`, symbol: "▤" },
          { label: "Contacts", href: `${base}/contacts`, symbol: "◎" },
          { label: "Insights", href: `${base}/analytics`, symbol: "▥" },
          ...(roleSatisfies(role, "admin")
            ? [
                {
                  label: "Request a change",
                  href: `${base}/settings/requests`,
                  symbol: <ChangeRequestIcon />,
                },
                {
                  label: "Team",
                  href: `${base}/settings/members`,
                  symbol: "♧",
                },
                {
                  label: "Tenant data and audit",
                  href: `${base}/settings/data`,
                  symbol: "▦",
                },
              ]
            : []),
        ]
      : [{ label: "Organizations", href: "/app", symbol: "↗" }];
  const destinations = [
    ...links,
    ...(!platform && me?.is_platform_staff
      ? [{ label: "Platform admin", href: "/platform", symbol: "↗" }]
      : []),
  ];
  const filtered = destinations.filter((link) =>
    link.label.toLowerCase().includes(query.toLowerCase()),
  );
  function openPalette() {
    drawer.current?.close();
    trigger.current = document.activeElement as HTMLElement;
    setQuery("");
    setSelected(0);
    palette.current?.showModal();
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  async function signOut() {
    await api.logout();
    await refresh();
    router.push("/login");
  }
  function active(href: string) {
    return (
      pathname === href ||
      (href !== base &&
        href !== "/platform" &&
        href !== "/app" &&
        pathname.startsWith(`${href}/`))
    );
  }
  const navigation = (
    <>
      <Link className="brand" href={platform ? "/platform" : "/app"}>
        <span className="brand-mark" aria-hidden="true">
          ✧
        </span>
        <span>
          Website Chatbot
          <small>{platform ? "Platform administration" : "AI workspace"}</small>
        </span>
      </Link>
      <p className="nav-caption">{platform ? "ADMINISTRATION" : "WORKSPACE"}</p>
      <nav
        aria-label={platform ? "Platform navigation" : "Workspace navigation"}
      >
        {destinations.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            title={link.label}
            aria-current={active(link.href) ? "page" : undefined}
            onClick={() => drawer.current?.close()}
          >
            <span aria-hidden="true" className="nav-symbol">
              {link.symbol}
            </span>
            <span>{link.label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <p className="muted">
          {platform
            ? "Staff tools · audited actions"
            : "Your conversations, connected."}
        </p>
        <ThemeToggle />
      </div>
    </>
  );
  return (
    <div
      className={`app-shell ${platform ? "platform-shell" : ""}`}
      data-collapsed={collapsed}
    >
      <a className="skip-link" href="#workspace-content">
        Skip to content
      </a>
      <aside className="sidebar">
        {navigation}
        <button
          className="quiet-button collapse-button"
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? "»" : "«"}
        </button>
      </aside>
      <div className="workspace-body">
        <header className="app-header">
          <button
            className="quiet-button mobile-menu"
            type="button"
            aria-label="Open navigation"
            onClick={() => drawer.current?.showModal()}
          >
            ☰
          </button>
          <span className="context-badge" data-testid="workspace-context">
            {platform
              ? "Platform admin"
              : tenantId
                ? `Client workspace · ${organizationName ?? "Workspace"} · ${role ?? "Checking access"}`
                : "Your organizations"}
          </span>
          <button
            className="quiet-button search-trigger"
            type="button"
            onClick={openPalette}
            aria-label="Open command palette"
          >
            Search pages <kbd>⌘ / Ctrl K</kbd>
          </button>
          {me && (
            <nav aria-label="Organization" className="account-nav">
              <label className="sr-only" htmlFor="org-selector">
                Organization
              </label>
              <select
                id="org-selector"
                aria-label="Organization selector"
                value={tenantId ?? ""}
                onChange={(event) => {
                  const id = event.target.value;
                  const archived =
                    me.is_platform_staff &&
                    staffOrganizations?.some(
                      (org) => org.id === id && org.status === "archived",
                    );
                  router.push(
                    archived
                      ? `/platform/clients/${id}`
                      : me.is_platform_staff
                        ? `/app/${id}/bots`
                        : `/app/${id}`,
                  );
                }}
              >
                {!tenantId && <option value="">Switch organization</option>}
                {organizations.map((m) => (
                  <option key={m.tenant_id} value={m.tenant_id}>
                    {m.tenant_name}
                  </option>
                ))}
              </select>
              {me.is_platform_staff && staffOrganizationsError && (
                <span role="alert">{staffOrganizationsError}</span>
              )}
              <button
                className="quiet-button"
                type="button"
                title={me.email}
                onClick={() => void signOut()}
              >
                Sign out
              </button>
            </nav>
          )}
        </header>
        <div id="workspace-content" className="workspace-content" tabIndex={-1}>
          <nav aria-label="Breadcrumb" className="breadcrumbs">
            <Link href={platform ? "/platform" : "/app"}>
              {platform ? "Platform" : "Workspaces"}
            </Link>
            <span aria-hidden="true">/</span>
            <span>
              {platform
                ? "Administration"
                : (organizationName ?? "Organizations")}
            </span>
            {tenantId && (
              <>
                <span aria-hidden="true">/</span>
                <span>
                  {links.find((link) => active(link.href))?.label ??
                    (me?.is_platform_staff ? "Bot workspace" : "Conversations")}
                </span>
              </>
            )}
          </nav>
          {children}
        </div>
      </div>
      <dialog
        ref={drawer}
        className="nav-drawer"
        aria-label="Workspace navigation"
        onClose={() => trigger.current?.focus()}
      >
        <button
          className="quiet-button"
          type="button"
          onClick={() => drawer.current?.close()}
        >
          Close navigation
        </button>
        {navigation}
      </dialog>
      <dialog
        ref={palette}
        className="command-palette"
        aria-labelledby="palette-title"
        onClose={() => trigger.current?.focus()}
      >
        <div className="dialog-heading">
          <h2 id="palette-title">Go to a page</h2>
          <button
            className="quiet-button"
            onClick={() => palette.current?.close()}
            type="button"
          >
            Close
          </button>
        </div>
        <label htmlFor="palette-query" className="sr-only">
          Search pages
        </label>
        <input
          id="palette-query"
          role="combobox"
          aria-expanded="true"
          aria-autocomplete="list"
          aria-activedescendant={
            filtered[selected] ? `palette-option-${selected}` : undefined
          }
          autoComplete="off"
          placeholder="Where would you like to go?"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setSelected((current) =>
                filtered.length
                  ? (current +
                      (event.key === "ArrowDown" ? 1 : -1) +
                      filtered.length) %
                    filtered.length
                  : 0,
              );
            }
            if (event.key === "Enter" && filtered[selected]) {
              event.preventDefault();
              router.push(filtered[selected].href);
              palette.current?.close();
            }
          }}
          aria-controls="palette-results"
          aria-describedby="palette-help"
        />
        <ul id="palette-results" role="listbox" aria-label="Pages">
          {filtered.map((link, index) => (
            <li key={link.href} role="presentation">
              <Link
                id={`palette-option-${index}`}
                role="option"
                aria-selected={selected === index}
                data-selected={selected === index}
                href={link.href}
                onClick={() => palette.current?.close()}
              >
                {link.symbol} {link.label}
                <span aria-hidden="true">✧</span>
              </Link>
            </li>
          ))}
        </ul>
        {!filtered.length && <p className="muted">No matching pages.</p>}
        <p id="palette-help" className="muted">
          Arrow keys to select · Enter to open · Escape to close
        </p>
      </dialog>
    </div>
  );
}

function ChangeRequestIcon() {
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9H13" />
      <path d="m16 3 5 5m-9 4 1-4 6-6 3 3-6 6-4 1Z" />
    </svg>
  );
}
