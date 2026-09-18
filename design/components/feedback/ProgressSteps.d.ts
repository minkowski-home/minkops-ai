export interface ProgressStepsProps {
  /** Number of segments. */
  total?: number;
  /** Zero-based index of the current step; all segments up to it are filled. */
  current?: number;
  style?: React.CSSProperties;
}

export declare function ProgressSteps(props: ProgressStepsProps): JSX.Element;
