import { createContext, useContext } from "react";

import type { User } from "../api";

// Shared auth state for the SPA: the session is a signed cookie (D-055), so the only client-side
// state is "who is `/api/me`". `VJA_AUTH_REQUIRED` stays off in 9.4 — anonymous is a valid state
// (the read API serves the default profile), so `user === null` is normal, not an error.
export interface AuthState {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
