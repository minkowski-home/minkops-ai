export interface SelectOption { value: string; label: string }

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** Options as data; ignored if children are supplied. */
  options?: SelectOption[];
  invalid?: boolean;
}

export declare function Select(props: SelectProps): JSX.Element;
