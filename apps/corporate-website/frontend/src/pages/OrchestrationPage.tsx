import { ACCESS_HREF } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { Card, ButtonLink, Eyebrow } from "../ui/primitives";

const LAYERS = [
  {
    eyebrow: "Employee and Workflow",
    title: "One shared memory",
    body: "An Employee is the product grouping. A Workflow defines a business outcome, its steps, and where a person reviews or decides."
  },
  {
    eyebrow: "Skills, tools and connectors",
    title: "One rulebook",
    body: "Skills describe procedures. Approved tools and connectors determine which files and external systems a Workflow can use."
  },
  {
    eyebrow: "Human review",
    title: "One way of working",
    body: "Approvals and decisions that need a person should be explicit, with a clear way to review what happened."
  }
] as const;

export default function OrchestrationPage() {
  return (
    <>
      <SeoHead
        title="How Minkops employees work together"
        description="Understand the Minkops model: AI Employees organized around defined Workflows, with skills, approved tools and human review."
        path="/orchestration"
      />

      <PageHero
        eyebrow="Teamwork"
        title="What happens between them."
        lead="Minkops groups AI Employees around Workflows. A Workflow describes the business outcome, the procedure and the approved systems it may use; people remain responsible for approvals and decisions that need judgment."
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

      <Section tone="sunken">
        <div className="mk-cta-band">
          <div className="mk-cta-band__text">
            <h2 className="mk-cta-band__title">
              Start with one. Add the next when you're ready.
            </h2>
            <p className="mk-cta-band__lead">
              Start with one repeatable process. Define its outcome, approved systems and
              human review points before treating it as ready to run.
            </p>
          </div>
          <div className="mk-cta-band__actions">
            <ButtonLink
              to={ACCESS_HREF}
              size="lg"
              variant="primary"
              iconRight={<Icon name="chevronRight" size={16} />}
            >
              Explore a workflow
            </ButtonLink>
          </div>
        </div>
      </Section>
    </>
  );
}
