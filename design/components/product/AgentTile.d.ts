/**
 * Marketing-side roster card for one AI employee.
 *
 * @startingPoint section="Website" subtitle="Agent roster tile" viewport="700x210"
 */
export interface AgentTileProps {
  /** Agent name — Ora, Eko, Floc, Cruz, Hosi, Prex, Kall, Leed, Kim, Insi, Imel. */
  name: string;
  /** The job it does, e.g. "Email handler". */
  tool: string;
  /** Vertical, e.g. "Generic", "Fast food". */
  domain?: string;
  /** Agent role glyph key from the Icon set. */
  glyph?: "designer" | "social" | "writer" | "manager" | "host" | "kitchen" | "support" | "sales" | "retail" | "analyst" | "email";
  /** Mono status line: "Live", "In build". */
  status?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}

export declare function AgentTile(props: AgentTileProps): JSX.Element;
