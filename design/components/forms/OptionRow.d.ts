export interface OptionRowProps {
  /** The choice text — sentence case, plain language. */
  label: string;
  /** Small mono meta line (a stage tag, an aside). */
  meta?: string;
  selected?: boolean;
  /** Square indicator + checkbox semantics instead of radio. */
  multi?: boolean;
  onSelect?: () => void;
  style?: React.CSSProperties;
}

export declare function OptionRow(props: OptionRowProps): JSX.Element;
