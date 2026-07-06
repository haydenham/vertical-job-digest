import { createContext, useContext } from "react";

import type { Profile, User } from "../api";

// Shared auth state for the SPA: the session is a signed cookie (D-055), so the client-side state is
// "who is `/api/me`" + "their one profile". The SPA routes on both (D-064/D-065): `user === null` →
// landing/login; `user` + `profile === null` → onboarding; `user` + `profile` → their dashboard.
export interface AuthState {
  user: User | null;
  profile: Profile | null;
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
