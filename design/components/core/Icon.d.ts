export type UiIconName =
  | "home" | "agents" | "tasks" | "analytics" | "settings"
  | "chevronLeft" | "chevronRight" | "send" | "bell" | "check" | "x"
  | "palette" | "logout";

export type AgentIconName =
  | "designer" | "social" | "writer" | "manager" | "host" | "kitchen"
  | "support" | "sales" | "retail" | "analyst" | "email";

export interface IconProps {
  /** Icon key — a UI glyph or an agent role glyph. */
  name: UiIconName | AgentIconName;
  /** Rendered square size in px. Default 18. */
  size?: number;
  /** Override the per-icon stroke width (UI icons 1.8–2.2, agent icons 1.65). */
  strokeWidth?: number | string;
  style?: React.CSSProperties;
}

export declare function Icon(props: IconProps): JSX.Element | null;
