import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type SessionUser } from "../api";
import { desktopBridge } from '../desktop/bridge';
import { reads } from "../readCache";

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
  const identity = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const current = await api<SessionUser | null>("/api/auth/session");
      if (identity.current !== (current?.id ?? null)) reads.clear();
      identity.current = current?.id ?? null;
      setUser(current);
      return current;
    } catch {
      reads.clear(); identity.current = null;
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
    reads.clear(); identity.current = null;
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
