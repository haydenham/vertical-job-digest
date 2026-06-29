import { useCallback, useEffect, useState, type ReactNode } from "react";

import { fetchMe, logout as apiLogout, type User } from "../api";
import { AuthContext } from "./useAuth";

// Probes `/api/me` once on mount and exposes the session state via the AuthContext. A failed probe
// (network/5xx) or a 401 just leaves us logged-out — anonymous is a valid state in 9.4.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setUser(await fetchMe());
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  useEffect(() => {
    refresh().catch(() => {
      setUser(null);
      setLoading(false);
    });
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>
  );
}
