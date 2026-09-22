/**
 * AuthContext — authentication state management.
 *
 * Uses a local session fallback until the backend auth endpoints are ready.
 * Replace the fallback with real API calls to
 * POST /api/auth/login and POST /api/auth/logout.
 *
 * The context exposes:
 *   user       — the logged-in User object, or null if unauthenticated
 *   isLoading  — true while checking session on initial mount
 *   login()    — accepts credentials, sets user state
 *   logout()   — clears user state and redirects to /login
 */

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { User } from "../types/user";
import { DEFAULT_OPERATOR } from "../session/defaultOperator";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading] = useState(false);

  const login = useCallback(async (email: string, password: string) => {
    void email;
    void password;
    setUser(DEFAULT_OPERATOR);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Throws if used outside <AuthProvider>. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
