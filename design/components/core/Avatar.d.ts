export interface AvatarProps {
  /** Full name — initials are derived from the first two words. */
  name: string;
  /** agent = graphite fill · human = light fill with border */
  kind?: "agent" | "human";
  /** Square size in px. Default 30. */
  size?: number;
  /** Rounded square (default) or circle. */
  square?: boolean;
  style?: React.CSSProperties;
}

export declare function Avatar(props: AvatarProps): JSX.Element;
