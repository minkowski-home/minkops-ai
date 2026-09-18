export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
  /** Grow with content up to --composer-max-h, then scroll. Used by the task composer. */
  autoGrow?: boolean;
}

export declare function Textarea(props: TextareaProps): JSX.Element;
