/**
 * A step in an orchestration diagram — one agent handing off to the next.
 *
 * @startingPoint section="Website" subtitle="Orchestration flow node and arrow" viewport="700x150"
 */
export interface FlowNodeProps {
  /** Agent name (omit for an output node). */
  agent?: string;
  /** Role beneath the name. */
  role?: string;
  /** Render as the terminal outcome: graphite fill, no Ember top edge. */
  output?: boolean;
  /** Label for an output node, e.g. "Published campaign". */
  label?: string;
  style?: React.CSSProperties;
}

export interface FlowArrowProps {
  /** The handoff, in mono: "Drafts copy", "Resolves ticket". */
  label?: string;
  style?: React.CSSProperties;
}

export declare function FlowNode(props: FlowNodeProps): JSX.Element;
export declare function FlowArrow(props: FlowArrowProps): JSX.Element;
