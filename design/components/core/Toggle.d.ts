export interface ToggleProps {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  /** Visible text label; also used as the input's aria-label. */
  label?: string;
  disabled?: boolean;
  id?: string;
  style?: React.CSSProperties;
}

export declare function Toggle(props: ToggleProps): JSX.Element;
