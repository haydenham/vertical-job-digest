import { useCallback, useEffect, useState, type ReactNode } from "react";

import { fetchMe, logout as apiLogout, type Me } from "../api";
import { AuthContext } from "./useAuth";

// Probes `/api/me` once on mount and exposes the session (user + their one profile) via the
// AuthContext. A 401 leaves us logged-out (`me === null`); `refresh()` is called after a résumé
// upload so a freshly-onboarded user's new profile lands before the dashboard routes on it.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const fresh = await fetchMe();
      setMe(fresh);
      return fresh;
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setMe(null);
  }, []);

  useEffect(() => {
    refresh().catch(() => {
      setMe(null);
      setLoading(false);
    });
  }, [refresh]);

  return (
    <AuthContext.Provider
      value={{ user: me?.user ?? null, profile: me?.profile ?? null, loading, refresh, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}
