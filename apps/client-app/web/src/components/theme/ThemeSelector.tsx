/**
 * ThemeSelector — header control for switching the site-wide theme.
 *
 * Renders a pill button that opens a dropdown popover listing all
 * available themes. Selecting a theme calls ThemeContext.setTheme(),
 * which applies the data-theme attribute to <html> and persists the
 * choice to localStorage. Because the CSS variables in tokens.css are
 * declared under [data-theme] selectors, the entire UI re-skins
 * instantly with zero JavaScript intervention beyond the setAttribute.
 *
 * The dropdown closes on outside click via a useEffect event listener.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { THEMES } from "@minkops/brand";
import { useTheme } from "../../contexts/ThemeContext";
import { IconPalette, IconCheck } from "../icons";
import "./ThemeSelector.css";

export default function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentConfig = THEMES.find((t) => t.name === theme) ?? THEMES[0];

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!open) return;
    function handleOutsideClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  const select = useCallback(
    (name: (typeof THEMES)[number]["name"]) => {
      setTheme(name);
      setOpen(false);
    },
    [setTheme]
  );

  return (
    <div className="theme-selector" ref={containerRef}>
      <button
        className="theme-selector-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Theme: ${currentConfig.label}`}
        title="Change theme"
      >
        <IconPalette size={14} />
        <span>{currentConfig.label}</span>
        <span className="theme-swatch" aria-hidden="true" />
      </button>

      {open && (
        <div
          className="theme-dropdown"
          role="listbox"
          aria-label="Select theme"
        >
          <div className="theme-dropdown-label">Theme</div>

          {THEMES.map((t) => (
            <button
              key={t.name}
              className={`theme-option${theme === t.name ? " active" : ""}`}
              role="option"
              aria-selected={theme === t.name}
              onClick={() => select(t.name)}
            >
              <div className={`theme-option-preview ${t.name}`} aria-hidden="true">
                <span className="theme-preview-dot" />
              </div>

              <div className="theme-option-text">
                <div className="theme-option-name">{t.label}</div>
                <div className="theme-option-desc">{t.description}</div>
              </div>

              <span className="theme-option-check" aria-hidden="true">
                <IconCheck size={13} />
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
