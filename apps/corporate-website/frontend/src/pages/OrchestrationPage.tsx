import { Fragment } from "react";
import { getAgent } from "../content/agents";
import { ACCESS_HREF } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { FlowArrow, FlowNode } from "../ui/product";
import { Badge, ButtonLink, Card, Eyebrow } from "../ui/primitives";

type Step = { agent: string; role: string } | { arrow: string } | { output: string };

type Flow = {
  number: string;
  title: string;
  story: string;
  steps: readonly Step[];
};

const FLOWS: readonly Flow[] = [
  {
    number: "01",
    title: "A campaign that writes and dresses itself",
    story:
      "Floc drafts the copy. Ora reads it and builds the visuals to match, without anyone writing a brief in between, because both of them already know the brand.",
    steps: [
      { agent: "Floc", role: "Copywriter" },
      { arrow: "Drafts the copy" },
      { agent: "Ora", role: "Visual designer" },
      { arrow: "Builds the assets" },
      { output: "Campaign ready to publish" }
    ]
  },
  {
    number: "02",
    title: "A complaint that doesn't go viral",
    story:
      "Eko spots that a public comment is really a support problem and hands it to Kall. Kall resolves it privately, then Eko closes the loop in public so everyone watching sees it handled.",
    steps: [
      { agent: "Eko", role: "Social handler" },
      { arrow: "Spots a complaint" },
      { agent: "Kall", role: "Support rep" },
      { arrow: "Resolves the ticket" },
      { agent: "Eko", role: "Social handler" }
    ]
  },
  {
    number: "03",
    title: "The order that never gets lost",
    story:
      "Hosi takes the order at the counter, Cruz routes it and keeps an eye on the whole shift, and Prex runs it through the kitchen. A manager only hears about what actually needs a manager.",
    steps: [
      { agent: "Hosi", role: "Front of house" },
      { arrow: "Takes the order" },
      { agent: "Cruz", role: "Shift manager" },
      { arrow: "Sends the ticket" },
      { agent: "Prex", role: "Kitchen" }
    ]
  }
];

const LAYERS = [
  {
    eyebrow: "Shared memory",
    title: "One shared memory",
    body: "Your policies, products, customers and history live in one place everyone on the team reads from. Kall already knows the customer before Eko finishes the handoff."
  },
  {
    eyebrow: "Shared rules",
    title: "One rulebook",
    body: "Every employee has an authority line, written by you: the refund it can approve, the discount it can't. Above that line, it stops and asks."
  },
  {
    eyebrow: "Shared rhythm",
    title: "One way of working",
    body: "Handoffs, to-do lists and questions for you all run the same way, so adding a role means hiring into a team, not bolting on another bot."
  }
] as const;

/**
 * A flow's shape in one line, e.g. "3 agents · 2 handoffs · 1 department".
 * Derived from the steps (and the roster, via getAgent) so it can't drift.
 */
function flowSummary(flow: Flow) {
  const agents = flow.steps.flatMap((step) =>
    "agent" in step ? [getAgent(step.agent)] : []
  );
  const people = new Set(agents.map((agent) => agent.name)).size;
  const departments = new Set(agents.map((agent) => agent.department)).size;
  const handoffs = flow.steps.filter((step) => "arrow" in step).length;
  const plural = (count: number, word: string) =>
    `${count} ${word}${count === 1 ? "" : "s"}`;
  return [
    plural(people, "employee"),
    plural(handoffs, "handoff"),
    plural(departments, "department")
  ].join(" · ");
}

export default function OrchestrationPage() {
  return (
    <>
      <SeoHead
        title="How Minkops employees work together"
        description="One employee is useful. The handoff is where it gets interesting. See how Minkops employees share one memory and one rulebook, and bring in a person only when it matters."
        path="/orchestration"
      />

      <PageHero
        eyebrow="Teamwork"
        title="What happens between them."
        lead="A single employee is useful. The interesting part is the handoff. Every Minkops employee reads from the same memory and answers to the same rules, so work moves from one to the next the way it would between colleagues who sit side by side. A person steps in only when a decision sits above an employee's authority."
      />

      <Section
        eyebrow="Three layers underneath"
        title="Why they don't talk past each other."
        tone="sunken"
      >
        <ul className="mk-layers">
          {LAYERS.map((layer) => (
            <li key={layer.title}>
              <Card className="mk-layers__card">
                <Eyebrow>{layer.eyebrow}</Eyebrow>
                <h3 className="mk-layers__title">{layer.title}</h3>
                <p className="mk-layers__body">{layer.body}</p>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        eyebrow="Handoffs in motion"
        title="Three flows, running as you read this."
        lead="A few of the handoffs happening across the team right now. Every arrow is one employee passing work to another with the context already attached, so nobody has to explain anything twice."
      >
        <ol className="mk-flows">
          {FLOWS.map((flow) => (
            <li key={flow.number} className="mk-flow">
              <div className="mk-flow__head">
                <span className="mk-flow__number">{flow.number}</span>
                <div className="mk-flow__text">
                  <h3 className="mk-flow__title">{flow.title}</h3>
                  <p className="mk-flow__story">{flow.story}</p>
                </div>
                <Badge className="mk-flow__status">{flowSummary(flow)}</Badge>
              </div>
              <div
                className="mk-flow__diagram"
                aria-label={`Flow ${flow.number} diagram`}
              >
                {flow.steps.map((step, index) => (
                  <Fragment key={index}>
                    {"arrow" in step ? (
                      <FlowArrow label={step.arrow} />
                    ) : "output" in step ? (
                      <FlowNode output={step.output} />
                    ) : (
                      <FlowNode agent={step.agent} role={step.role} />
                    )}
                  </Fragment>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section tone="sunken">
        <div className="mk-cta-band">
          <div className="mk-cta-band__text">
            <h2 className="mk-cta-band__title">
              Start with one. Add the next when you're ready.
            </h2>
            <p className="mk-cta-band__lead">
              Most teams begin with the inbox or the support queue, because that's where
              the hours go first. The rest join the same team whenever you want them.
            </p>
          </div>
          <div className="mk-cta-band__actions">
            <ButtonLink
              to={ACCESS_HREF}
              size="lg"
              variant="primary"
              iconRight={<Icon name="chevronRight" size={16} />}
            >
              Build your team
            </ButtonLink>
          </div>
        </div>
      </Section>
    </>
  );
}
