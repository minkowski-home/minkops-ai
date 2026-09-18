export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Alert-red border for failed validation. */
  invalid?: boolean;
  /** Render the value in IBM Plex Mono — for ids, keys, and numeric entry. */
  mono?: boolean;
  /** sm 30px · md 38px */
  size?: "sm" | "md";
}

export declare function Input(props: InputProps): JSX.Element;
