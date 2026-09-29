export const THEMES = [
  { id: "minkops-light", label: "Minkops Light" },
  { id: "minkops-dark", label: "Minkops Dark" },
  { id: "slate-light", label: "Slate Light" },
  { id: "slate-dark", label: "Slate Dark" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

export function resolveTheme(value: string | null): ThemeId {
  return THEMES.find((theme) => theme.id === value)?.id ?? "minkops-light";
}
