/**
 * Session.
 *
 * `is_internal` on the authenticated user decides which of the two route trees
 * loads. Role checks here are UX affordances only — the server re-reads the
 * user row on every request and remains the security boundary.
 */
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, onAuthLost, tokens } from "@/api/client";
import { qk } from "@/api/queries";
import type { AuthenticatedUser, LoginResponse, RoleCode, SignupRequest } from "@/api/types";

interface AuthValue {
  user: AuthenticatedUser | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (email: string, password: string) => Promise<AuthenticatedUser>;
  signup: (body: SignupRequest) => Promise<AuthenticatedUser>;
  logout: () => void;
}

/**
 * Where the app should land once a session is established.
 *
 * Two things can decide the destination after a login: the component that
 * triggered it, and a route guard reacting to the new user landing on a route
 * that is no longer legal for them (an internal user sitting on /portal, or the
 * reverse). React Router's location lives in its own external store, so those
 * two updates do not batch — whichever renders last wins, and that ordering is
 * not deterministic.
 *
 * Rather than race, the caller states its intent here and every redirect
 * authority reads it. The value is consumed once so it cannot leak into a
 * later navigation.
 */
let intendedLanding: string | null = null;

export const setIntendedLanding = (to: string | null) => {
  intendedLanding = to;
};

/**
 * Read without consuming.
 *
 * Guards read this during render, and render must stay pure — React invokes it
 * twice under StrictMode, so a read-and-clear would hand the value to the
 * discarded pass and leave the real one with nothing. `LandingIntent` clears it
 * from an effect once the app has actually arrived.
 */
export const peekIntendedLanding = (): string | null => intendedLanding;

export const clearIntendedLanding = () => {
  intendedLanding = null;
};

const Ctx = React.createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = React.useState<AuthenticatedUser | null>(null);
  const [status, setStatus] = React.useState<AuthValue["status"]>(
    tokens.access() ? "loading" : "anonymous",
  );

  // Restore a session from sessionStorage on boot.
  React.useEffect(() => {
    if (!tokens.access()) return;
    let cancelled = false;
    api
      .get<AuthenticatedUser>("/users/me")
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        tokens.clear();
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The client fires this when a refresh fails; drop straight to the login screen.
  React.useEffect(() => {
    const off = onAuthLost(() => {
      setUser(null);
      setStatus("anonymous");
      qc.clear();
    });
    return () => {
      off();
    };
  }, [qc]);

  /**
   * Swap the session atomically.
   *
   * The token, the cache and the user all change together, and `status` only
   * ever moves *to* "authenticated" — it never dips through "anonymous". That
   * matters for switching account in place: a momentary anonymous state would
   * let the route guard bounce the user to /login mid-switch.
   */
  const adopt = React.useCallback(
    (res: LoginResponse) => {
      tokens.set(res.tokens);
      // The incoming role must not read the outgoing role's cached data.
      qc.clear();
      setUser(res.user);
      setStatus("authenticated");
      qc.setQueryData(qk.me, res.user);
      return res.user;
    },
    [qc],
  );

  const value = React.useMemo<AuthValue>(
    () => ({
      user,
      status,
      login: async (email, password) =>
        adopt(await api.post<LoginResponse>("/auth/login", { email, password }, { raw: true })),
      signup: async (body) => adopt(await api.post<LoginResponse>("/auth/signup", body, { raw: true })),
      logout: () => {
        // The API has no logout endpoint; the session is client-side state.
        setIntendedLanding(null);
        tokens.clear();
        setUser(null);
        setStatus("anonymous");
        qc.clear();
      },
    }),
    [user, status, adopt, qc],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = React.useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

/* -- capability helpers ---------------------------------------------------
   Mirrors of the backend dependency guards, used to decide what to *show*.
   Every call still handles a 403. */
export const CAN = {
  authorQuotes: ["SALES", "MANAGER", "ADMIN"],
  approve: ["MANAGER", "FINANCE", "ADMIN"],
  allocate: ["OPS", "SALES", "ADMIN"],
  fulfill: ["OPS", "ADMIN"],
  billing: ["FINANCE", "ADMIN"],
  administer: ["ADMIN"],
  promise: ["SALES", "MANAGER", "ADMIN"],
} satisfies Record<string, readonly RoleCode[]>;

const has = (role: RoleCode | undefined, allowed: readonly RoleCode[]) =>
  Boolean(role && (allowed as readonly string[]).includes(role));

export const useCan = () => {
  const { user } = useAuth();
  const role = user?.role;
  return React.useMemo(
    () => ({
      role,
      is: (...roles: RoleCode[]) => Boolean(role && roles.includes(role)),
      authorQuotes: has(role, CAN.authorQuotes),
      approve: has(role, CAN.approve),
      allocate: has(role, CAN.allocate),
      fulfill: has(role, CAN.fulfill),
      billing: has(role, CAN.billing),
      administer: has(role, CAN.administer),
      promise: has(role, CAN.promise),
    }),
    [role],
  );
};
