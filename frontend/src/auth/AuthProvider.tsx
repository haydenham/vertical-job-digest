import { useCallback, useEffect, useState, type ReactNode } from "react";

import { fetchMe, logout as apiLogout, type Me } from "../api";
import { AuthContext } from "./useAuth";

// Probes `/api/me` once on mount and exposes the session (user + their one profile) via the
// AuthContext. A 401 leaves us logged-out (`me === null`); `refresh()` is called after a résumé
// upload so a freshly-onboarded user's new profile lands before the dashboard routes on it.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(false);

  const refresh = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) {
      setLoading(true);
      setAuthError(false);
    }
    try {
      const fresh = await fetchMe();
      setMe(fresh);
      setAuthError(false);
      return fresh;
    } catch (error: unknown) {
      // A 401 is represented by `fetchMe()` as a successful `null`. Anything thrown is a real
      // account-probe failure and must never masquerade as logged-out / Landing (D-083).
      if (!opts?.silent) setAuthError(true);
      throw error;
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setMe(null);
    setAuthError(false);
  }, []);

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  return (
    <AuthContext.Provider
      value={{
        user: me?.user ?? null,
        profile: me?.profile ?? null,
        loading,
        authError,
        refresh,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
