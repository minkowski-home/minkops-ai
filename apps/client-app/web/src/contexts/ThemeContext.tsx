/**
 * ThemeContext — site-wide theme management.
 *
 * Persists the selected theme to localStorage and applies it as a
 * `data-theme` attribute on the root <html> element. The CSS variable
 * definitions in shared/brand/tokens.css respond to this attribute,
 * so a single React state change instantly re-skins every component
 * across the app without any component-level logic.
 *
 * Applying the attribute to <html> (not <body> or a subtree) ensures
 * that CSS custom properties cascade everywhere, including portals and
 * modals rendered outside the React root.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode
} from "react";
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  type ThemeName
} from "@minkops/brand";

interface ThemeContextValue {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialTheme(): ThemeName {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as ThemeName | null;
    if (stored === "light" || stored === "dark" || stored === "minkowski") return stored;
  } catch {
    // localStorage unavailable (e.g. SSR or private-browsing restrictions)
  }
  return DEFAULT_THEME;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(getInitialTheme);

  // Sync the data-theme attribute on <html> whenever theme changes
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // ignore storage errors
    }
  }, [theme]);

  const setTheme = useCallback((next: ThemeName) => {
    setThemeState(next);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}
