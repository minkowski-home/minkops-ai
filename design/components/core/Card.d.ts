export interface CardProps {
  /** default = white + hairline · sunken = tinted · inverse = graphite band · accent = Ember wash */
  tone?: "default" | "sunken" | "inverse" | "accent";
  /** Padding override; defaults to the --pad-card token (16px). */
  pad?: string;
  /** 2px Ember left edge — reserved for items awaiting a human. */
  accentEdge?: boolean;
  /** Adds --shadow-pop. Only for things that genuinely float. */
  elevated?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Card(props: CardProps): JSX.Element;
