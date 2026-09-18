/**
 * The Minkops action control. Rust fill for the one primary action per view;
 * everything else is a bordered secondary or a ghost.
 *
 * @startingPoint section="Core" subtitle="Action controls in all five variants" viewport="700x180"
 */
export interface ButtonProps {
  /** primary = Rust fill (one per view) · secondary = bordered · ghost = bare · inverse = on dark · danger = destructive */
  variant?: "primary" | "secondary" | "ghost" | "inverse" | "danger";
  /** sm 28px · md 36px · lg 46px (marketing CTAs) */
  size?: "sm" | "md" | "lg";
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  disabled?: boolean;
  fullWidth?: boolean;
  type?: "button" | "submit" | "reset";
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Button(props: ButtonProps): JSX.Element;
