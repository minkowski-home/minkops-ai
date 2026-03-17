export type AgentIllustration =
  | "designer"
  | "social"
  | "writer"
  | "manager"
  | "host"
  | "kitchen"
  | "support"
  | "sales"
  | "retail"
  | "analyst"
  | "email";

export type DirectoryAgent = {
  persona: string;
  name: string;
  tool: string;
  domain: string;
  color: string;
  illustration: AgentIllustration;
};

export const AGENT_DIRECTORY: DirectoryAgent[] = [
  {
    persona: "Bianca",
    name: "Ora",
    tool: "Moodboard Generator",
    domain: "Interior Design",
    color: "#9180bc",
    illustration: "designer"
  },
  {
    persona: "Ryan",
    name: "Eko",
    tool: "Social Media Handler",
    domain: "Generic",
    color: "#78a9c8",
    illustration: "social"
  },
  {
    persona: "Ethan",
    name: "Floc",
    tool: "Content Creator",
    domain: "Generic",
    color: "#d28b76",
    illustration: "writer"
  },
  {
    persona: "Devin",
    name: "Cruz",
    tool: "Manager's Assistant",
    domain: "Fast Food",
    color: "#7a7f8f",
    illustration: "manager"
  },
  {
    persona: "Emily",
    name: "Hosi",
    tool: "Front of House",
    domain: "Fast Food",
    color: "#c8ae78",
    illustration: "host"
  },
  {
    persona: "Tony",
    name: "Prex",
    tool: "Back of House",
    domain: "Fast Food",
    color: "#c98a70",
    illustration: "kitchen"
  },
  {
    persona: "Jaina",
    name: "Kall",
    tool: "Customer Support Rep",
    domain: "Generic",
    color: "#cf8ea8",
    illustration: "support"
  },
  {
    persona: "Sarah",
    name: "Leed",
    tool: "Lead Generation Caller",
    domain: "Generic",
    color: "#d39a87",
    illustration: "sales"
  },
  {
    persona: "Kim",
    name: "Kim",
    tool: "Store Manager's Assistant",
    domain: "Generic",
    color: "#8ea591",
    illustration: "retail"
  },
  {
    persona: "Mark",
    name: "Insi",
    tool: "Business Analyst",
    domain: "Generic",
    color: "#7ea8a6",
    illustration: "analyst"
  },
  {
    persona: "Nathan",
    name: "Imel",
    tool: "Email Handler",
    domain: "Generic",
    color: "#c8a07d",
    illustration: "email"
  }
];

export function getAgentByName(name: string) {
  return AGENT_DIRECTORY.find((agent) => agent.name === name);
}
