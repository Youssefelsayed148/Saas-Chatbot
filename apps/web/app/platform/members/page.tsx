"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import {
  OrganizationSelect,
  PasswordPanel,
  RoleSelect,
} from "@/lib/staff-members";
import {
  Button,
  DataTable,
  Field,
  FormSection,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import "@/app/staff-screens.css";

const COMMON_COUNTRY_CODES = [
  "+20",
  "+966",
  "+971",
  "+974",
  "+968",
  "+965",
  "+973",
  "+962",
  "+961",
  "+90",
  "+44",
  "+49",
  "+33",
  "+34",
  "+39",
  "+1",
];

function joinedPhone(countryCode: string, national: string): string {
  // Digits only: the API normalizes separators too, but keep the payload clean.
  const value = national.trim().replace(/[\s().-]/g, "");
  if (!value) return "";
  // Already international → send as typed (the API still validates E.164).
  if (value.startsWith("+")) return value;
  // A country is always selected (default +20): a pasted national number
  // starting with 0 loses that trunk prefix.
  const digits = value.replace(/^0+/, "");
  return digits ? `${countryCode}${digits}` : "";
}

export default function MembersPage() {
  const [users, setUsers] = useState<api.StaffUser[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [filterOrg, setFilterOrg] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [email, setEmail] = useState("");
  const [countryCode, setCountryCode] = useState("+20");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [generate, setGenerate] = useState(false);
  const [issued, setIssued] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState<api.ClientRole>("viewer");
  const [error, setError] = useState("");
  const [phoneFieldError, setPhoneFieldError] = useState<string | null>(null);
  const [emailFieldError, setEmailFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const params = new URLSearchParams({
      q: query,
      limit: "25",
      offset: String(offset),
    });
    if (filterOrg) params.set("organization_id", filterOrg);
    if (status) params.set("status", status);
    const result = await api.platformUsers(params.toString());
    setUsers(result.users);
    setTotal(result.total);
  }, [query, filterOrg, status, offset]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load().catch(() => setError("Could not load members."));
    }, 200);
    return () => clearTimeout(timer);
  }, [load]);
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setPhoneFieldError(null);
    setEmailFieldError(null);
    setIssued("");
    try {
      const result = await api.platformCreateUser({
        email,
        phone: joinedPhone(countryCode, phone) || undefined,
        ...(generate ? { generate: true } : { password }),
        ...(organization ? { organization_id: organization, role } : {}),
      });
      setIssued(result.generated_password ?? password);
      setPassword("");
      setEmail("");
      setPhone("");
      await load();
    } catch (e) {
      if (e instanceof api.ApiError && e.fieldErrors.length > 0) {
        // Field details go inline under the matching input; anything without a
        // matching input stays in the form-level error area.
        const phone = e.fieldErrors.find((entry) => entry.field === "phone");
        const emailEntry = e.fieldErrors.find(
          (entry) => entry.field === "email",
        );
        if (phone) setPhoneFieldError(phone.message);
        if (emailEntry) setEmailFieldError(emailEntry.message);
        if (
          e.fieldErrors.some(
            (entry) => entry.field !== "phone" && entry.field !== "email",
          )
        ) {
          setError(e.message);
        }
      } else {
        setError(e instanceof Error ? e.message : "Could not create user.");
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="staff-page">
      <PageHeader
        title="Members"
        purpose="Every user across all organizations. Search, filter and create accounts."
      />
      {error && <Notice tone="error" message={error} />}
      <section aria-label="Filter members" className="filter-bar">
        <Field label="Search email">
          {(control) => (
            <input
              {...control}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          )}
        </Field>
        <OrganizationSelect
          optional
          emptyLabel="All organizations"
          activeOnly={false}
          value={filterOrg}
          onChange={(id) => {
            setFilterOrg(id);
            setOffset(0);
          }}
        />
        <Field label="Status">
          {(control) => (
            <select
              {...control}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          )}
        </Field>
      </section>
      <DataTable
        caption="Member directory"
        rows={users}
        rowKey={(user) => user.id}
        columns={[
          {
            key: "email",
            header: "Email",
            cell: (user) => (
              <Link href={`/platform/members/${user.id}`}>
                <bdi dir="ltr">{user.email}</bdi>
              </Link>
            ),
          },
          {
            key: "phone",
            header: "Phone",
            cell: (user) =>
              user.phone ? <bdi dir="ltr">{user.phone}</bdi> : "—",
          },
          {
            key: "status",
            header: "Status",
            cell: (user) => (
              <StatusBadge
                value={user.is_active ? "active" : "inactive"}
                tone={user.is_active ? "success" : "neutral"}
              >
                {user.is_active ? "Active" : "Inactive"}
              </StatusBadge>
            ),
          },
          {
            key: "organizations",
            header: "Organizations",
            cell: (user) => (
              <ul className="chip-list">
                {user.memberships.map((m) => (
                  <li key={m.organization_id}>
                    {`${m.organization_name}: ${m.role} (${m.status})`}
                  </li>
                ))}
              </ul>
            ),
          },
          {
            key: "created",
            header: "Created",
            cell: (user) => new Date(user.created_at).toLocaleDateString(),
          },
        ]}
      />
      <div className="pager">
        <p>{total} members</p>
        <div className="action-row">
          <Button
            variant="quiet"
            disabled={!offset}
            onClick={() => setOffset(offset - 25)}
          >
            Previous
          </Button>
          <Button
            variant="quiet"
            disabled={offset + 25 >= total}
            onClick={() => setOffset(offset + 25)}
          >
            Next
          </Button>
        </div>
      </div>
      <FormSection
        title="Create user"
        description="Creates an account staff can hand over. Add an organization to give access straight away."
      >
        <form
          onSubmit={(e) => {
            void create(e);
          }}
        >
          <Field
            label="Email"
            error={emailFieldError}
            errorTestId="email-field-error"
          >
            {(control) => (
              <input
                {...control}
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <div className="phone-row">
            <Field label="Country code">
              {(control) => (
                <select
                  {...control}
                  value={countryCode}
                  dir="ltr"
                  disabled={busy}
                  onChange={(e) => setCountryCode(e.target.value)}
                >
                  {COMMON_COUNTRY_CODES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field
              label="Phone"
              hint="Enter the number without the leading 0."
              error={phoneFieldError}
              errorTestId="phone-field-error"
            >
              {(control) => (
                <input
                  {...control}
                  type="tel"
                  dir="ltr"
                  value={phone}
                  disabled={busy}
                  onChange={(e) => setPhone(e.target.value)}
                />
              )}
            </Field>
          </div>
          <Field
            label="Password"
            hint={
              generate
                ? "A strong password will be generated when the user is created."
                : "At least 8 characters."
            }
          >
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
          <OrganizationSelect
            optional
            value={organization}
            onChange={setOrganization}
          />
          {organization && <RoleSelect value={role} onChange={setRole} />}
          <Button type="submit" disabled={busy}>
            Create user
          </Button>
        </form>
      </FormSection>
      {issued && (
        <PasswordPanel password={issued} onDismiss={() => setIssued("")} />
      )}
    </main>
  );
}
