import { FUNNEL_HREF, SITE } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { ButtonLink, Card, Eyebrow } from "../ui/primitives";

const FACTS = [
  { figure: "01", label: "Employee · the product grouping" },
  {
    figure: "02",
    label: "Workflow · the defined unit of business work"
  },
  {
    figure: "03",
    label: "Skills, tools and connectors · procedure and approved access"
  }
] as const;

const PRINCIPLES = [
  {
    title: "If we haven't used it, we won't sell it",
    body: "We use our own businesses to understand practical work and the review points people need. Product examples remain illustrative until an integration is verified."
  },
  {
    title: "Quiet is the goal",
    body: "A useful Workflow has a defined outcome, the necessary steps and clear points where someone should review or decide."
  },
  {
    title: "People above the line",
    body: "Access follows the approved tools and connectors. Decisions that need a person should be explicit and reviewable."
  }
] as const;

const FAMILY = [
  {
    name: "Minkowski Home",
    href: SITE.links.minkowskiHome,
    body: "An interior product design business in the Minkops family."
  },
  {
    name: "Myndral",
    href: SITE.links.myndral,
    body: "A curated music label in the Minkops family."
  }
] as const;

export default function AboutPage() {
  return (
    <>
      <SeoHead
        title="About"
        description="How Minkops thinks about AI Employees, business Workflows, approved tools and human review."
        path="/about"
      />

      <PageHero
        eyebrow="About"
        title="We run our own company on it first."
        lead="Minkops organizes AI Employees around practical business Workflows. We focus on clear outcomes, explicit access and review points that keep people responsible for their decisions."
      >
        <dl className="mk-facts">
          {FACTS.map((fact) => (
            <div key={fact.label} className="mk-facts__item">
              <dt className="mk-facts__figure">{fact.figure}</dt>
              <dd className="mk-facts__label">{fact.label}</dd>
            </div>
          ))}
        </dl>
      </PageHero>

      <Section
        eyebrow="Where it started"
        title="It began with a furniture company."
        tone="sunken"
      >
        <div className="mk-prose">
          <p>
            Minkowski Home started as an interior product design company, with a long-term
            picture of connected furniture and a design ecosystem where everything fits
            together. As the plans grew, the work grew faster than the team did.
          </p>
          <p>
            That work led us to focus on repeatable processes: what outcome is needed,
            which steps lead to it, and what a person should review. We describe that unit
            of work as a Workflow.
          </p>
          <p>
            An AI Employee is the product grouping around that work. Skills describe
            procedures; approved tools and connectors determine which files and external
            systems a Workflow can use.
          </p>
          <p>
            We keep a human decision-maker in the loop for approvals and outcomes that
            need judgment. Examples on this site describe possible designs, not live
            integrations or measured customer results.
          </p>
        </div>
      </Section>

      <Section eyebrow="How we work" title="Three things we won't compromise on.">
        <ol className="mk-principles">
          {PRINCIPLES.map((principle, index) => (
            <li key={principle.title} className="mk-principles__item">
              <span className="mk-principles__number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mk-principles__title">{principle.title}</h3>
              <p className="mk-principles__body">{principle.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        eyebrow="The family"
        title="A product of Minkowski Home."
        lead="Minkops sits alongside two very different businesses. Their work gives us useful context, while each Workflow still needs its own permissions, verification and review rules."
        tone="sunken"
      >
        <ul className="mk-family">
          {FAMILY.map((member) => (
            <li key={member.name}>
              <Card className="mk-family__card">
                <h3 className="mk-family__name">{member.name}</h3>
                <p className="mk-family__body">{member.body}</p>
                <a href={member.href} target="_blank" rel="noopener noreferrer">
                  Visit {member.name}
                </a>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section>
        <div className="mk-cta-band">
          <div className="mk-cta-band__text">
            <Eyebrow>Your turn</Eyebrow>
            <h2 className="mk-cta-band__title">
              Curious what it would take off your plate?
            </h2>
            <p className="mk-cta-band__lead">
              Tell us about a process you want to improve and we’ll outline a workflow to
              discuss. The example is not a live integration or a savings estimate.
            </p>
          </div>
          <div className="mk-cta-band__actions">
            <ButtonLink
              to={FUNNEL_HREF}
              size="lg"
              variant="primary"
              iconRight={<Icon name="chevronRight" size={16} />}
            >
              Explore a workflow
            </ButtonLink>
            <ButtonLink
              to={`mailto:${SITE.emails.general}`}
              size="lg"
              variant="secondary"
            >
              Write to us
            </ButtonLink>
          </div>
        </div>
      </Section>
    </>
  );
}
