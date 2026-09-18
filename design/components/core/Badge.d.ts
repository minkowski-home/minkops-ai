export interface BadgeProps {
  /** Semantic tone. Interrupt types map 1:1: approval · escalation · review · error. */
  tone?: "neutral" | "approval" | "escalation" | "review" | "error" | "ok" | "warn";
  /** Uppercase mono label (default). Set false for sentence-case text badges. */
  mono?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Badge(props: BadgeProps): JSX.Element;
