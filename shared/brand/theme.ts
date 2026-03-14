/**
 * Minkops Brand — Theme Type Definitions
 *
 * Consumed by all apps in the monorepo. This file is the single
 * authoritative source for what theme names are valid and how they
 * are described. The actual CSS tokens live in tokens.css.
 */

export type ThemeName = "light" | "dark" | "minkowski";

export interface ThemeConfig {
  /** Machine-readable identifier; maps directly to `data-theme` attribute value. */
  name: ThemeName;
  /** Display label shown in the theme selector UI. */
  label: string;
  /** Short description shown as a subtitle in the theme selector. */
  description: string;
}

/** Ordered list of all available themes. */
export const THEMES: ThemeConfig[] = [
  {
    name: "light",
    label: "Light",
    description: "Clean, glassy, luminous"
  },
  {
    name: "dark",
    label: "Dark",
    description: "Deep dark with pink/blue palette"
  },
  {
    name: "minkowski",
    label: "Minkowski",
    description: "Warm ivory & parchment, burgundy accents"
  }
];

export const DEFAULT_THEME: ThemeName = "light";
export const THEME_STORAGE_KEY = "minkops-theme";
