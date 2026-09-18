export interface StatusDotProps {
  /** Runtime state of an agent, run, or service. */
  status?: "active" | "idle" | "disabled" | "error" | "ok";
  /** Diameter in px. Default 7. */
  size?: number;
  /** Adds a soft tinted halo — reserve for "live right now". */
  pulse?: boolean;
  /** Optional uppercase mono label rendered beside the dot. */
  label?: string;
  style?: React.CSSProperties;
}

export declare function StatusDot(props: StatusDotProps): JSX.Element;
