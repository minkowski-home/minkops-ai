import React from "react";

/* Path data copied verbatim from the Minkops codebase icon set
   (apps/client-app/web/src/components/icons/index.tsx) and the agent role
   glyphs in apps/corporate-website (AgentRosterCard.tsx). The same files are
   available as standalone SVGs in assets/icons/. */
const UI = {
  home: ["1.8", <><path d="M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z" /><path d="M9 21V12h6v9" /></>],
  agents: ["1.8", <><rect x="3" y="8" width="18" height="12" rx="2" /><path d="M8 8V6a4 4 0 0 1 8 0v2" /><circle cx="9" cy="14" r="1" fill="currentColor" stroke="none" /><circle cx="15" cy="14" r="1" fill="currentColor" stroke="none" /><path d="M9 17c.667.667 1.333 1 3 1s2.333-.333 3-1" /></>],
  tasks: ["1.8", <><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12l2 2 4-4" /></>],
  analytics: ["1.8", <><path d="M3 3v18h18" /><path d="M7 16l4-6 4 4 4-8" /></>],
  settings: ["1.8", <><circle cx="12" cy="12" r="3" /><path d="M12 2v2m0 16v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M2 12h2m16 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></>],
  chevronLeft: ["2", <path d="M15 18l-6-6 6-6" />],
  chevronRight: ["2", <path d="M9 18l6-6-6-6" />],
  send: ["1.8", <><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></>],
  bell: ["1.8", <><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></>],
  check: ["2.2", <polyline points="20 6 9 17 4 12" />],
  x: ["2", <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>],
  palette: ["1.8", <><circle cx="13.5" cy="6.5" r="1" fill="currentColor" stroke="none" /><circle cx="17.5" cy="10.5" r="1" fill="currentColor" stroke="none" /><circle cx="8.5" cy="7.5" r="1" fill="currentColor" stroke="none" /><circle cx="6.5" cy="12.5" r="1" fill="currentColor" stroke="none" /><path d="M12 2C6.5 2 2 6.5 2 12a10 10 0 0 0 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" /></>],
  logout: ["1.8", <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></>]
};

const AGENT = {
  designer: <><path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17 6.5L18 7.5L20.5 5" /><path d="M17.25 11.75L20.5 12.75L18.75 15.75L16 14.75Z" /></>,
  social: <><path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17.5 8.25H20.5V11.25H18.75L17.5 12.5V8.25Z" /><path d="M3.5 10.25H6.5V13.25H4.75L3.5 14.5V10.25Z" /></>,
  writer: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M7.5 18.5L8.75 13L12 11.75L15.25 13L16.5 18.5" /><path d="M15.75 10.5L19.75 8.75" /><path d="M17 12.5L20.5 11.75" /></>,
  manager: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M8 18.5V14.25C8 12.73 9.23 11.5 10.75 11.5H13.25C14.77 11.5 16 12.73 16 14.25V18.5" /><path d="M12 11.5V16.5" /><path d="M10.75 13L12 14.25L13.25 13" /></>,
  host: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M12 11.5V18.5" /><path d="M12 12L6 14.75" /><path d="M12 12L18 14.75" /><path d="M9.5 18.5H14.5" /></>,
  kitchen: <><path d="M8.5 8.25C8.5 6.18 10.18 4.5 12.25 4.5C14.32 4.5 16 6.18 16 8.25V9.5H8.5V8.25Z" /><path d="M9.25 6.75A2.75 2.75 0 1 0 14.75 6.75A2.75 2.75 0 0 0 9.25 6.75Z" /><path d="M8.25 18.5V13.5C8.25 11.84 9.59 10.5 11.25 10.5H12.75C14.41 10.5 15.75 11.84 15.75 13.5V18.5" /></>,
  support: <><path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M7 10.5A5 5 0 0 1 17 10.5" /><path d="M6.5 11.5V14" /><path d="M17.5 11.5V14" /><path d="M17.5 14C17.5 15.66 16.16 17 14.5 17H13.75" /></>,
  sales: <><path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17.5 8.5L20 11L17.5 13.5" /><path d="M20 11H15.75" /></>,
  retail: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17.25 9.25H20.5V15.5H17.25Z" /><path d="M18.75 11H19" /></>,
  analyst: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17.25 15.5V11.5" /><path d="M19 15.5V9.5" /><path d="M20.75 15.5V13" /></>,
  email: <><path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" /><path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" /><path d="M17.25 10H20.5V14H17.25Z" /><path d="M17.25 10L18.88 11.5L20.5 10" /></>
};

export function Icon({ name, size = 18, strokeWidth, style, ...rest }) {
  const isAgent = name in AGENT;
  const entry = isAgent ? ["1.65", AGENT[name]] : UI[name];
  if (!entry) return null;
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth ?? entry[0]} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" style={{ display: "block", flex: "none", ...style }} {...rest}
    >
      {entry[1]}
    </svg>
  );
}
