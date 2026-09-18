export interface PriorityPillProps {
  /** Severity — drives the dot and text colour. */
  level?: "critical" | "high" | "medium" | "low";
  /** Optional leading count, e.g. `2 critical`. */
  count?: number;
  /** Label override; defaults to the level name. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function PriorityPill(props: PriorityPillProps): JSX.Element;
