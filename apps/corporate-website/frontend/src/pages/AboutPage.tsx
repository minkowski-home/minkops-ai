import { FUNNEL_HREF, SITE } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { ButtonLink, Card, Eyebrow } from "../ui/primitives";

const FACTS = [
  { figure: "01", label: "A curated music label" },
  {
    figure: "02",
    label: "Original fictional artists and releases"
  },
  {
    figure: "03",
    label: "One shared musical universe"
  }
] as const;

const PRINCIPLES = [
  {
    title: "If we haven't used it, we won't sell it",
    body: "We start with work we understand from our own businesses, and stay clear about what’s real and what’s only an example."
  },
  {
    title: "Quiet is the goal",
    body: "Good software should handle repeat work quietly and bring a person in when judgment matters."
  },
  {
    title: "People above the line",
    body: "You decide what can happen on its own and when it should ask you."
  }
] as const;

const FAMILY = [
  {
    name: "Myndral",
    href: SITE.links.myndral,
    body: "A curated label for original fictional artists, music and stories that share one world."
  }
] as const;

export default function AboutPage() {
  return (
    <>
      <SeoHead
        title="About"
        description="Minkops grew from the work around Myndral, a curated music label built around original fictional artists and a shared story world."
        path="/about"
      />

      <PageHero
        eyebrow="About"
        title="We run our own company on it first."
        lead="Minkops grew from the work around Myndral, our curated music label. We’re exploring practical ways to help small teams with repeat work, while people stay in charge of important decisions."
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
        title="It began with Myndral."
        tone="sunken"
      >
        <div className="mk-prose">
          <p>
            Myndral is a curated label built around original fictional artists, music and
            a shared story world. Every release is chosen and cared for as part of that
            universe.
          </p>
          <p>
            A growing creative business also brings plenty of practical work behind the
            scenes. We started asking how software could help a small team with the
            repeat work, without taking important decisions away from people.
          </p>
          <p>
            That question became Minkops: practical software for business work that
            comes around again and again.
          </p>
          <p>
            The examples on this site show ideas we could explore together. They are not
            claims that Myndral uses these workflows today or that we have measured a
            particular result.
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
        title="Myndral, from Minkops AI."
        lead="Myndral is a curated music label from Minkops AI, built around original artists and a catalogue with one shared story world."
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
              Tell us what you wish took less time. We’ll talk about what to hand off and
              where you want to stay involved.
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
