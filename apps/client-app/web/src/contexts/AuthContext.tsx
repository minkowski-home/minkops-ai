/**
 * AuthContext — authentication state management.
 *
 * Currently uses mock data. When the backend auth endpoints are ready,
 * replace the mock login/logout logic with real API calls to
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
import { MOCK_USER } from "../mock/user";

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

  const login = useCallback(async (_email: string, _password: string) => {
    // TODO: replace with POST /api/auth/login
    // Simulate network latency
    await new Promise((resolve) => setTimeout(resolve, 600));
    setUser(MOCK_USER);
  }, []);

  const logout = useCallback(() => {
    // TODO: replace with POST /api/auth/logout
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
