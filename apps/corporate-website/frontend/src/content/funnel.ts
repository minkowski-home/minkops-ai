/* Intake questions and illustrative workflow outlines for the home page. */

export type QuestionKind = "single" | "multi";

export type FunnelOption = {
  value: string;
  label: string;
  meta?: string;
};

export type FunnelQuestion = {
  id: "business" | "timeSinks" | "bottleneck" | "systems";
  kicker: string;
  question: string;
  subtext: string;
  kind: QuestionKind;
  options: readonly FunnelOption[];
};

export type WorkArea = "support" | "leads" | "email" | "social" | "ads" | "analytics";

export const QUESTIONS: readonly FunnelQuestion[] = [
  {
    id: "business",
    kicker: "Step 01 / Your business",
    question: "What kind of work does your business do?",
    subtext: "This helps us choose an example closer to your day-to-day.",
    kind: "single",
    options: [
      { value: "retail", label: "Retail and online sales" },
      { value: "construction", label: "Construction and field work" },
      { value: "hospitality", label: "Food and hospitality" },
      { value: "services", label: "Professional services" },
      { value: "creative", label: "Creative and media" },
      { value: "other", label: "Something else" }
    ]
  },
  {
    id: "timeSinks",
    kicker: "Step 02 / Repeatable work",
    question: "Where does your week actually disappear?",
    subtext: "Pick the work that pulls you away from higher-priority tasks.",
    kind: "multi",
    options: [
      { value: "support", label: "Answering customer questions" },
      { value: "leads", label: "Following up with prospects" },
      { value: "email", label: "Sorting and responding to email" },
      { value: "social", label: "Preparing social content" },
      { value: "ads", label: "Preparing marketing material" },
      { value: "analytics", label: "Collecting information and reports" }
    ]
  },
  {
    id: "bottleneck",
    kicker: "Step 03 / Priority",
    question: "If one of these improved, which would matter most?",
    subtext: "We’ll use this as the starting point for an outline.",
    kind: "single",
    options: [
      { value: "support", label: "The steady stream of support questions" },
      { value: "leads", label: "Leads that go cold after they browse" },
      { value: "email", label: "The inbox that never quite reaches zero" },
      { value: "social", label: "Showing up on social every single week" },
      { value: "ads", label: "Ad creative that earns its budget" },
      { value: "analytics", label: "Knowing which numbers matter this week" }
    ]
  },
  {
    id: "systems",
    kicker: "Step 04 / Existing tools",
    question: "Where does this work happen today?",
    subtext: "A workflow should fit the systems and permissions you already have.",
    kind: "single",
    options: [
      { value: "email", label: "Email or a shared inbox" },
      { value: "sheets", label: "Spreadsheets" },
      { value: "business-app", label: "A business app or CRM" },
      { value: "messages", label: "Chat or messaging" },
      { value: "unknown", label: "A mix, or I’m not sure yet" }
    ]
  }
];

export type FunnelAnswers = {
  business?: string;
  timeSinks?: string[];
  bottleneck?: string;
  systems?: string;
};

type Recommendation = {
  name: string;
  description: string;
};

const RECOMMENDATIONS: Record<WorkArea, Recommendation> = {
  support: {
    name: "Customer support workflow",
    description:
      "Gather the request and relevant context, draft a response, then pause for approval when policy requires it."
  },
  leads: {
    name: "Lead follow-up workflow",
    description:
      "Collect an enquiry, check it against qualification rules, prepare a follow-up and record the outcome."
  },
  email: {
    name: "Shared inbox workflow",
    description:
      "Classify an incoming message, find approved context, draft a reply and route exceptions to a person."
  },
  social: {
    name: "Social content workflow",
    description:
      "Prepare content from an approved brief, check it against brand guidance and leave publishing for review."
  },
  ads: {
    name: "Marketing preparation workflow",
    description:
      "Turn a campaign brief into draft copy and creative directions for a person to review."
  },
  analytics: {
    name: "Reporting workflow",
    description:
      "Gather approved source data, check it for gaps and prepare a concise report for review."
  }
};

export type FunnelResult = {
  businessLabel: string;
  primaryArea: WorkArea;
  primary: Recommendation;
  supporting: Recommendation[];
};

function isWorkArea(value: string | undefined): value is WorkArea {
  return value !== undefined && value in RECOMMENDATIONS;
}

export function buildResult(answers: FunnelAnswers): FunnelResult {
  const sinks = (answers.timeSinks ?? []).filter(isWorkArea);
  const primaryKey: WorkArea = isWorkArea(answers.bottleneck)
    ? answers.bottleneck
    : (sinks[0] ?? "support");
  const business = QUESTIONS.find((question) => question.id === "business");
  const businessLabel =
    business?.options.find((option) => option.value === answers.business)?.label ??
    "Your business";

  return {
    businessLabel,
    primaryArea: primaryKey,
    primary: RECOMMENDATIONS[primaryKey],
    supporting: sinks
      .filter((key) => key !== primaryKey)
      .slice(0, 2)
      .map((key) => RECOMMENDATIONS[key])
  };
}
