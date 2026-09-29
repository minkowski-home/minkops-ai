import { createContext, useContext, useLayoutEffect, useState } from "react";
import { resolveTheme, THEMES, type ThemeId } from "./options";

const ThemeContext = createContext<{
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<ThemeId>(() => {
    try { return resolveTheme(localStorage.getItem("minkops.theme")); }
    catch { return "minkops-light"; }
  });

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("minkops.theme", theme); } catch { /* Browsing without storage still works. */ }
  }, [theme]);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function ThemePicker() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("ThemePicker requires ThemeProvider");
  return <label className="theme-picker">
    <span>Theme</span>
    <select aria-label="Theme" value={context.theme}
      onChange={(event) => context.setTheme(resolveTheme(event.target.value))}>
      {THEMES.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
    </select>
  </label>;
}
