/**
 * One agent in the console's roster pane: identity, live status, last-active
 * time, and an enable switch.
 *
 * @startingPoint section="Console" subtitle="Agent roster row with status and switch" viewport="700x220"
 */
export interface AgentRowProps {
  /** Agent name, e.g. "Imel". */
  name: string;
  /** One-line role, e.g. "Email handler". */
  role?: string;
  status?: "active" | "idle" | "disabled" | "error";
  /** Pre-formatted relative time: "4m ago", "never". */
  lastActive?: string;
  enabled?: boolean;
  selected?: boolean;
  onToggle?: (enabled: boolean) => void;
  onSelect?: () => void;
  style?: React.CSSProperties;
}

export declare function AgentRow(props: AgentRowProps): JSX.Element;
