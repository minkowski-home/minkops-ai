import type { ReactNode, SVGProps } from "react";

/*
 * The Minkops icon set, copied verbatim from the design system
 * (design/components/core/Icon.jsx, design/assets/icons/). Two families share
 * one 24x24 grid: UI glyphs, and agent role glyphs built on a common
 * head-and-shoulders motif. Do not add glyphs from another library. A new mark
 * should extend the existing motif at the same stroke weight.
 */

const UI_GLYPHS = {
  home: {
    stroke: 1.8,
    body: (
      <>
        <path d="M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z" />
        <path d="M9 21V12h6v9" />
      </>
    )
  },
  chevronLeft: { stroke: 2, body: <path d="M15 18l-6-6 6-6" /> },
  chevronRight: { stroke: 2, body: <path d="M9 18l6-6-6-6" /> },
  send: {
    stroke: 1.8,
    body: (
      <>
        <line x1="22" y1="2" x2="11" y2="13" />
        <polygon points="22 2 15 22 11 13 2 9 22 2" />
      </>
    )
  },
  bell: {
    stroke: 1.8,
    body: (
      <>
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </>
    )
  },
  check: { stroke: 2.2, body: <polyline points="20 6 9 17 4 12" /> },
  /* Built like "x" below: same 2px stroke, same end points on the 24px grid. */
  plus: {
    stroke: 2,
    body: (
      <>
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </>
    )
  },
  x: {
    stroke: 2,
    body: (
      <>
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </>
    )
  }
} satisfies Record<string, { stroke: number; body: ReactNode }>;

const AGENT_GLYPHS = {
  designer: (
    <>
      <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17 6.5L18 7.5L20.5 5" />
      <path d="M17.25 11.75L20.5 12.75L18.75 15.75L16 14.75Z" />
    </>
  ),
  social: (
    <>
      <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.5 8.25H20.5V11.25H18.75L17.5 12.5V8.25Z" />
      <path d="M3.5 10.25H6.5V13.25H4.75L3.5 14.5V10.25Z" />
    </>
  ),
  writer: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M7.5 18.5L8.75 13L12 11.75L15.25 13L16.5 18.5" />
      <path d="M15.75 10.5L19.75 8.75" />
      <path d="M17 12.5L20.5 11.75" />
    </>
  ),
  manager: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.25C8 12.73 9.23 11.5 10.75 11.5H13.25C14.77 11.5 16 12.73 16 14.25V18.5" />
      <path d="M12 11.5V16.5" />
      <path d="M10.75 13L12 14.25L13.25 13" />
    </>
  ),
  host: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M12 11.5V18.5" />
      <path d="M12 12L6 14.75" />
      <path d="M12 12L18 14.75" />
      <path d="M9.5 18.5H14.5" />
    </>
  ),
  kitchen: (
    <>
      <path d="M8.5 8.25C8.5 6.18 10.18 4.5 12.25 4.5C14.32 4.5 16 6.18 16 8.25V9.5H8.5V8.25Z" />
      <path d="M9.25 6.75A2.75 2.75 0 1 0 14.75 6.75A2.75 2.75 0 0 0 9.25 6.75Z" />
      <path d="M8.25 18.5V13.5C8.25 11.84 9.59 10.5 11.25 10.5H12.75C14.41 10.5 15.75 11.84 15.75 13.5V18.5" />
    </>
  ),
  support: (
    <>
      <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M7 10.5A5 5 0 0 1 17 10.5" />
      <path d="M6.5 11.5V14" />
      <path d="M17.5 11.5V14" />
      <path d="M17.5 14C17.5 15.66 16.16 17 14.5 17H13.75" />
    </>
  ),
  sales: (
    <>
      <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.5 8.5L20 11L17.5 13.5" />
      <path d="M20 11H15.75" />
    </>
  ),
  retail: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.25 9.25H20.5V15.5H17.25Z" />
      <path d="M18.75 11H19" />
    </>
  ),
  analyst: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.25 15.5V11.5" />
      <path d="M19 15.5V9.5" />
      <path d="M20.75 15.5V13" />
    </>
  ),
  email: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.25 10H20.5V14H17.25Z" />
      <path d="M17.25 10L18.88 11.5L20.5 10" />
    </>
  ),
  /* Added for the construction, finance and staffing roles. Same head-and-shoulders
     motif and 1.65 stroke; the modifier sits where the others put theirs. */
  builder: (
    <>
      <path d="M9.25 8.5A2.75 2.75 0 1 1 14.75 8.5A2.75 2.75 0 0 1 9.25 8.5Z" />
      <path d="M9 5.75C9 4.1 10.3 3 12 3C13.7 3 15 4.1 15 5.75" />
      <path d="M8 5.75H16" />
      <path d="M8 18.5V14.75C8 13.09 9.34 11.75 11 11.75H13C14.66 11.75 16 13.09 16 14.75V18.5" />
    </>
  ),
  ledger: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17.25 8.75H20.75V15.75H17.25Z" />
      <path d="M18.25 11H19.75" />
      <path d="M18.25 13.5H19.75" />
    </>
  ),
  scheduler: (
    <>
      <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
      <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
      <path d="M17 9.5H21V14.75H17Z" />
      <path d="M17 11.25H21" />
      <path d="M18.25 8.5V10" />
      <path d="M19.75 8.5V10" />
    </>
  )
} satisfies Record<string, ReactNode>;

const AGENT_STROKE = 1.65;

export type UiGlyph = keyof typeof UI_GLYPHS;
export type AgentGlyph = keyof typeof AGENT_GLYPHS;
export type IconName = UiGlyph | AgentGlyph;

type IconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: IconName;
  size?: number;
};

function isAgentGlyph(name: IconName): name is AgentGlyph {
  return name in AGENT_GLYPHS;
}

/** Decorative by default (aria-hidden); pair with visible text for meaning. */
export function Icon({ name, size = 18, strokeWidth, className, ...rest }: IconProps) {
  const [stroke, body] = isAgentGlyph(name)
    ? [AGENT_STROKE, AGENT_GLYPHS[name]]
    : [UI_GLYPHS[name].stroke, UI_GLYPHS[name].body];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth ?? stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={["mk-icon", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {body}
    </svg>
  );
}
