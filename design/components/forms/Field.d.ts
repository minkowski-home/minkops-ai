export interface FieldProps {
  /** Field label — sentence case, no colon. */
  label?: string;
  /** id of the control it labels. */
  htmlFor?: string;
  /** Helper text below the control. Hidden while `error` is set. */
  hint?: string;
  /** Error message; replaces the hint and turns it alert-red. */
  error?: string;
  /** Appends an Ember asterisk to the label. */
  required?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Field(props: FieldProps): JSX.Element;
