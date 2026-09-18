export interface MessageBubbleProps {
  /** human = graphite bubble, right-aligned · agent = tinted bubble, left-aligned */
  role?: "human" | "agent";
  /** Display name shown above the bubble ("You", "Imel"). */
  sender: string;
  content: string;
  /** Pre-formatted clock time: "14:32". */
  time?: string;
  style?: React.CSSProperties;
}

export declare function MessageBubble(props: MessageBubbleProps): JSX.Element;
