"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import {
  OrganizationSelect,
  PasswordPanel,
  RoleSelect,
} from "@/lib/staff-members";
import { Notice } from "@/lib/ui";

export default function MembersPage() {
  const [users, setUsers] = useState<api.StaffUser[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [filterOrg, setFilterOrg] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [generate, setGenerate] = useState(false);
  const [issued, setIssued] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState<api.ClientRole>("viewer");
  const [error, setError] = useState("");
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
    setIssued("");
    try {
      const result = await api.platformCreateUser({
        email,
        phone: phone || undefined,
        ...(generate ? { generate: true } : { password }),
        ...(organization ? { organization_id: organization, role } : {}),
      });
      setIssued(result.generated_password ?? password);
      setPassword("");
      setEmail("");
      setPhone("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create user.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>Members</h1>
      {error && <Notice tone="error" message={error} />}
      <section aria-label="Filter members">
        <label>
          Search email
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
          />
        </label>
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
        <label>
          Status
          <select
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
        </label>
      </section>
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Phone</th>
            <th>Status</th>
            <th>Organizations</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>
                <Link href={`/platform/members/${user.id}`}>{user.email}</Link>
              </td>
              <td>{user.phone ?? "—"}</td>
              <td>{user.is_active ? "Active" : "Inactive"}</td>
              <td>
                {user.memberships
                  .map((m) => `${m.organization_name}: ${m.role} (${m.status})`)
                  .join(", ")}
              </td>
              <td>{new Date(user.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>{total} members</p>
      <button disabled={!offset} onClick={() => setOffset(offset - 25)}>
        Previous
      </button>
      <button
        disabled={offset + 25 >= total}
        onClick={() => setOffset(offset + 25)}
      >
        Next
      </button>
      <section aria-label="Create user">
        <h2>Create user</h2>
        <form
          onSubmit={(e) => {
            void create(e);
          }}
        >
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Phone
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
          <label>
            Password
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
          {generate && (
            <p>A strong password will be generated when the user is created.</p>
          )}
          <OrganizationSelect
            optional
            value={organization}
            onChange={setOrganization}
          />
          {organization && <RoleSelect value={role} onChange={setRole} />}
          <button disabled={busy}>Create user</button>
        </form>
      </section>
      {issued && (
        <PasswordPanel password={issued} onDismiss={() => setIssued("")} />
      )}
    </>
  );
}
