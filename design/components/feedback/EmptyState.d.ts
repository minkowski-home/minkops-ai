export interface EmptyStateProps {
  /** An <Icon> — rendered in a bordered 36px tile. */
  icon?: React.ReactNode;
  /** Short factual headline: "All clear", "No tasks yet". */
  headline: string;
  /** One sentence explaining what would fill this space. */
  hint?: string;
  /** Optional single action. */
  action?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function EmptyState(props: EmptyStateProps): JSX.Element;
