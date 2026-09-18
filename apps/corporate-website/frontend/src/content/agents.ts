import type { AgentGlyph } from "../ui/Icon";

/**
 * The Minkops roster: the single source of truth for every agent the site
 * mentions. The roster, hero, funnel, orchestration diagrams and console
 * illustration all read from here, so a new hire is a one-entry change.
 */

/**
 * The team an agent sits in. This is the roster's primary grouping: it stays
 * meaningful whether there are fourteen agents or a hundred, where a flat grid
 * doesn't. Order here is display order for the roster filters.
 */
export const DEPARTMENTS = [
  "Front office",
  "Sales",
  "Marketing",
  "Back office",
  "Operations",
  "Construction",
  "Restaurant"
] as const;

export type Department = (typeof DEPARTMENTS)[number];

export type Agent = {
  name: string;
  role: string;
  department: Department;
  glyph: AgentGlyph;
  /** What the agent is doing right now, shown on its roster card. Present tense, one line. */
  now: string;
};

export const AGENTS: readonly Agent[] = [
  {
    name: "Imel",
    role: "Email handler",
    department: "Front office",
    glyph: "email",
    now: "Sorting 23 new emails"
  },
  {
    name: "Kall",
    role: "Customer support rep",
    department: "Front office",
    glyph: "support",
    now: "Closing a refund ticket"
  },
  {
    name: "Leed",
    role: "Lead generation caller",
    department: "Sales",
    glyph: "sales",
    now: "Calling back an abandoned cart"
  },
  {
    name: "Eko",
    role: "Social media handler",
    department: "Marketing",
    glyph: "social",
    now: "Replying to comments on a reel"
  },
  {
    name: "Floc",
    role: "Content creator",
    department: "Marketing",
    glyph: "writer",
    now: "Drafting Friday's launch captions"
  },
  {
    name: "Ora",
    role: "Visual designer",
    department: "Marketing",
    glyph: "designer",
    now: "Building an autumn moodboard"
  },
  {
    name: "Insi",
    role: "Business analyst",
    department: "Back office",
    glyph: "analyst",
    now: "Refreshing this week's numbers"
  },
  {
    name: "Tali",
    role: "Bookkeeper",
    department: "Back office",
    glyph: "ledger",
    now: "Matching supplier bills in Tally"
  },
  {
    name: "Rota",
    role: "Staffing coordinator",
    department: "Operations",
    glyph: "scheduler",
    now: "Filling a 10pm shift"
  },
  {
    name: "Kim",
    role: "Store manager's assistant",
    department: "Operations",
    glyph: "retail",
    now: "Counting stock before a delivery"
  },
  {
    name: "Sito",
    role: "Site coordinator",
    department: "Construction",
    glyph: "builder",
    now: "Reading the Site B WhatsApp group"
  },
  {
    name: "Cruz",
    role: "Shift manager",
    department: "Restaurant",
    glyph: "manager",
    now: "Checking the lunch rush forecast"
  },
  {
    name: "Hosi",
    role: "Front of house",
    department: "Restaurant",
    glyph: "host",
    now: "Taking an order at the counter"
  },
  {
    name: "Prex",
    role: "Back of house",
    department: "Restaurant",
    glyph: "kitchen",
    now: "Sending a ticket to the grill"
  }
];

export function getAgent(name: string): Agent {
  const agent = AGENTS.find((candidate) => candidate.name === name);
  if (!agent) {
    throw new Error(`Unknown agent "${name}". Add it to AGENTS before referencing it.`);
  }
  return agent;
}
