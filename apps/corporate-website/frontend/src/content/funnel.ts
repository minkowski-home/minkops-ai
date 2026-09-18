import { getAgent, type Agent } from "./agents";

/*
 * The "find your agent stack" questionnaire: four questions, one
 * recommendation. Question copy, the agent mapping and the recovery maths
 * live here as data and pure functions so the UI stays a thin renderer and
 * the estimate logic can be reasoned about (and tested) on its own.
 */

export type QuestionKind = "single" | "multi";

export type FunnelOption = {
  value: string;
  label: string;
  meta?: string;
};

export type FunnelQuestion = {
  id: "revenue" | "timeSinks" | "bottleneck" | "hours";
  kicker: string;
  question: string;
  subtext: string;
  kind: QuestionKind;
  options: readonly FunnelOption[];
};

/** Keys shared by the "time sink" and "bottleneck" questions. */
export type WorkArea = "support" | "leads" | "email" | "social" | "ads" | "analytics";

export const QUESTIONS: readonly FunnelQuestion[] = [
  {
    id: "revenue",
    kicker: "Step 01 / Your store",
    question: "Roughly what does your store bring in each month?",
    subtext: "A ballpark is plenty. It tells us how much you're juggling.",
    kind: "single",
    options: [
      { value: "early", label: "Under $2,000", meta: "Just getting going" },
      { value: "growth", label: "$2,000 to $15,000", meta: "Finding its feet" },
      { value: "scaling", label: "$15,000 to $75,000", meta: "Stretching the team" },
      { value: "established", label: "$75,000 or more", meta: "A proper operation" }
    ]
  },
  {
    id: "timeSinks",
    kicker: "Step 02 / Time audit",
    question: "Where does your week actually disappear?",
    subtext:
      "Pick everything that pulls you away from the work you started the store to do.",
    kind: "multi",
    options: [
      { value: "support", label: "Answering support tickets and customer calls" },
      { value: "leads", label: "Chasing abandoned carts and quiet leads" },
      { value: "email", label: "Keeping up with the inbox and email campaigns" },
      { value: "social", label: "Making something to post on social, again" },
      { value: "ads", label: "Writing ad copy and creative" },
      { value: "analytics", label: "Pulling reports and working out what they mean" }
    ]
  },
  {
    id: "bottleneck",
    kicker: "Step 03 / The big one",
    question: "If one of these vanished tomorrow, which would you pick?",
    subtext: "Your answer decides who we'd hire first.",
    kind: "single",
    options: [
      { value: "support", label: "The steady stream of support questions" },
      { value: "leads", label: "Leads that go cold after they browse" },
      { value: "email", label: "The inbox that never quite reaches zero" },
      { value: "social", label: "Showing up on social every single week" },
      { value: "ads", label: "Ad creative that actually earns its budget" },
      { value: "analytics", label: "Knowing which numbers matter this week" }
    ]
  },
  {
    id: "hours",
    kicker: "Step 04 / Hours",
    question: "How many hours a week go into all of that?",
    subtext: "Be honest. This is where the maths starts.",
    kind: "single",
    options: [
      { value: "2", label: "Under 2 hours", meta: "A light lift" },
      { value: "8", label: "2 to 8 hours", meta: "About a full day" },
      { value: "15", label: "8 to 15 hours", meta: "Nearly half your week" },
      { value: "20", label: "15 hours or more", meta: "A second job, really" }
    ]
  }
];

export type FunnelAnswers = {
  revenue?: string;
  timeSinks?: string[];
  bottleneck?: string;
  hours?: string;
};

type Recommendation = {
  agent: Agent;
  pitch: string;
  /** Typical weekly hours this role absorbs, as a range. An estimate, not a promise. */
  typicalSaving: string;
};

const RECOMMENDATIONS: Record<WorkArea, Recommendation> = {
  support: {
    agent: getAgent("Kall"),
    pitch:
      "Picks up each support ticket, works out what the customer actually needs, resolves it and updates the record. Anything above its authority lands on your desk with an answer already drafted.",
    typicalSaving: "8–12 hrs / wk"
  },
  leads: {
    agent: getAgent("Leed"),
    pitch:
      "Follows up on abandoned carts and quiet browsers within minutes, while they still remember why they came.",
    typicalSaving: "4–7 hrs / wk"
  },
  email: {
    agent: getAgent("Imel"),
    pitch:
      "Reads every email that lands, sorts the routine from the tricky, and drafts replies with the real order details in them, usually before you've opened your laptop.",
    typicalSaving: "5–9 hrs / wk"
  },
  social: {
    agent: getAgent("Eko"),
    pitch:
      "Keeps your channels fed with posts that sound like you, and notices when a comment is really a complaint.",
    typicalSaving: "4–6 hrs / wk"
  },
  ads: {
    agent: getAgent("Floc"),
    pitch:
      "Drafts ad copy and content in several directions, so you get to pick the good one instead of staring at a blank page.",
    typicalSaving: "3–5 hrs / wk"
  },
  analytics: {
    agent: getAgent("Insi"),
    pitch:
      "Reads your numbers across channels and tells you, in plain words, what changed and what deserves your attention this week.",
    typicalSaving: "3–4 hrs / wk"
  }
};

export const STAGE_LABEL: Record<string, string> = {
  early: "Early-stage store",
  growth: "Growing store",
  scaling: "Scaling store",
  established: "Established store"
};

/*
 * Recovery estimate. We assume an agent absorbs 45–70% of the hours the
 * visitor reported. The band is deliberately conservative and is shown to
 * the visitor alongside the result, so the number never floats free of its basis.
 */
export const RECOVERY_BAND = { low: 0.45, high: 0.7 } as const;

export type FunnelResult = {
  stageLabel: string;
  /** The band the visitor picked, as they saw it ("8 to 15 hours"). */
  reportedBand: string;
  /** The single figure the estimate is computed from: the top of that band. */
  reportedHours: number;
  recovered: { low: number; high: number };
  recoveredLabel: string;
  /** The work area the recommendation answers, e.g. to pre-fill the access form. */
  primaryArea: WorkArea;
  primary: Recommendation;
  supporting: Recommendation[];
};

function isWorkArea(value: string | undefined): value is WorkArea {
  return value !== undefined && value in RECOMMENDATIONS;
}

function formatHours(low: number, high: number) {
  if (high <= 1) return "about an hour";
  if (low === high) return `about ${high} hours`;
  return `${low}–${high} hours`;
}

export function buildResult(answers: FunnelAnswers): FunnelResult {
  const sinks = (answers.timeSinks ?? []).filter(isWorkArea);
  const primaryKey: WorkArea = isWorkArea(answers.bottleneck)
    ? answers.bottleneck
    : (sinks[0] ?? "support");

  const hoursQuestion = QUESTIONS.find((question) => question.id === "hours");
  const hoursOption = hoursQuestion?.options.find(
    (option) => option.value === answers.hours
  );
  const reportedHours = Number.parseInt(hoursOption?.value ?? "8", 10);
  const low = Math.max(1, Math.round(reportedHours * RECOVERY_BAND.low));
  const high = Math.max(low, Math.round(reportedHours * RECOVERY_BAND.high));

  return {
    stageLabel: STAGE_LABEL[answers.revenue ?? ""] ?? "Your store",
    reportedBand: (hoursOption?.label ?? "2 to 8 hours").toLowerCase(),
    reportedHours,
    recovered: { low, high },
    recoveredLabel: formatHours(low, high),
    primaryArea: primaryKey,
    primary: RECOMMENDATIONS[primaryKey],
    supporting: sinks
      .filter((key) => key !== primaryKey)
      .slice(0, 2)
      .map((key) => RECOMMENDATIONS[key])
  };
}
