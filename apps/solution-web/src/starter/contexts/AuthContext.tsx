import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type SessionUser } from "../api";
import { desktopBridge } from '../desktop/bridge';

interface AuthContextValue {
  user: SessionUser | null;
  isLoading: boolean;
  refresh: () => Promise<SessionUser | null>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [isLoading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const current = await api<SessionUser | null>("/api/auth/session");
      setUser(current);
      return current;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    await refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await desktopBridge()?.disconnect();
    if (user) await api("/api/auth/logout", { method: "POST" }, user.csrf_token);
    setUser(null);
  }, [user]);

  return <AuthContext.Provider value={{ user, isLoading, refresh, login, logout }}>
    {children}
  </AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
