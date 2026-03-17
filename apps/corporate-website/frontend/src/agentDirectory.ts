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
  name: string;
  tool: string;
  domain: string;
  color: string;
  illustration: AgentIllustration;
};

export const AGENT_DIRECTORY: DirectoryAgent[] = [
  {
    name: "Ora",
    tool: "Moodboard Generator",
    domain: "Interior Design",
    color: "#8e76d8",
    illustration: "designer"
  },
  {
    name: "Eko",
    tool: "Social Media Handler",
    domain: "Generic",
    color: "#63abd5",
    illustration: "social"
  },
  {
    name: "Floc",
    tool: "Content Creator",
    domain: "Generic",
    color: "#df8660",
    illustration: "writer"
  },
  {
    name: "Cruz",
    tool: "Manager's Assistant",
    domain: "Fast Food",
    color: "#6a7084",
    illustration: "manager"
  },
  {
    name: "Hosi",
    tool: "Front of House",
    domain: "Fast Food",
    color: "#d6b366",
    illustration: "host"
  },
  {
    name: "Prex",
    tool: "Back of House",
    domain: "Fast Food",
    color: "#de8b61",
    illustration: "kitchen"
  },
  {
    name: "Kall",
    tool: "Customer Support Rep",
    domain: "Generic",
    color: "#dd7f9e",
    illustration: "support"
  },
  {
    name: "Leed",
    tool: "Lead Generation Caller",
    domain: "Generic",
    color: "#de916d",
    illustration: "sales"
  },
  {
    name: "Kim",
    tool: "Store Manager's Assistant",
    domain: "Generic",
    color: "#86a889",
    illustration: "retail"
  },
  {
    name: "Insi",
    tool: "Business Analyst",
    domain: "Generic",
    color: "#69a9a5",
    illustration: "analyst"
  },
  {
    name: "Imel",
    tool: "Email Handler",
    domain: "Generic",
    color: "#cf996e",
    illustration: "email"
  }
];

export function getAgentByName(name: string) {
  return AGENT_DIRECTORY.find((agent) => agent.name === name);
}
