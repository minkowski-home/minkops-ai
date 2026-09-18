export interface IconButtonProps {
  /** Required — becomes both aria-label and title. */
  label: string;
  /** Square hit area in px. Default 32; use 44 for touch surfaces. */
  size?: number;
  /** Persistent selected state (Ember tint + Rust glyph). */
  active?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function IconButton(props: IconButtonProps): JSX.Element;
