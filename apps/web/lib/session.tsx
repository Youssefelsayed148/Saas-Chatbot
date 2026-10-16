"use client";

/** Session context: loads /me once, exposes role helpers for the dashboard. */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { ReactNode } from "react";

import * as api from "./api";
import type { ApiError, Me, Role } from "./api";

const ROLE_LEVEL: Record<Role, number> = {
  viewer: 1,
  editor: 2,
  admin: 3,
};

interface SessionState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<Me | null>;
  roleIn: (tenantId: string) => Role | null;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const refresh = useCallback(async (): Promise<Me | null> => {
    try {
      const nextMe = await api.me();
      setMe(nextMe);
      setError(null);
      return nextMe;
    } catch (caught) {
      // An invalid or expired session is simply "signed out"; the UI then
      // redirects to /login instead of rendering an error.
      setMe(null);
      if (isSessionError(caught)) {
        const here = `${window.location.pathname}${window.location.search}`;
        if (here.startsWith("/app") || here.startsWith("/platform")) {
          router.replace(`/login?next=${encodeURIComponent(here)}`);
        }
      } else {
        setError(
          caught instanceof Error ? caught.message : "Unexpected error.",
        );
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const onExpired = (): void => {
      const here = `${window.location.pathname}${window.location.search}`;
      const worth =
        here.startsWith("/app") || here.startsWith("/accept-invite");
      router.push(worth ? `/login?next=${encodeURIComponent(here)}` : "/login");
    };
    window.addEventListener("session-expired", onExpired);
    // Defer the initial fetch to avoid synchronous state updates in the effect.
    const timer = setTimeout(() => {
      void refresh();
    }, 0);
    return () => {
      window.removeEventListener("session-expired", onExpired);
      clearTimeout(timer);
    };
  }, [refresh, router]);

  const roleIn = useCallback(
    (tenantId: string): Role | null => {
      if (!me) return null;
      if (me.is_platform_staff) return "admin";
      const membership = me.memberships.find(
        (row) => row.tenant_id === tenantId,
      );
      return membership ? membership.role : null;
    },
    [me],
  );

  return (
    <SessionContext.Provider value={{ me, loading, error, refresh, roleIn }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const state = useContext(SessionContext);
  if (!state)
    throw new Error("useSession must be used inside <SessionProvider />.");
  return state;
}

export function roleSatisfies(current: Role | null, minimum: Role): boolean {
  if (!current) return false;
  return ROLE_LEVEL[current] >= ROLE_LEVEL[minimum];
}

export function isSessionError(error: unknown): error is ApiError {
  const candidate = error as ApiError;
  return (
    candidate instanceof Error &&
    candidate.name === "ApiError" &&
    (candidate.status === 401 || candidate.code === "UNAUTHENTICATED")
  );
}
