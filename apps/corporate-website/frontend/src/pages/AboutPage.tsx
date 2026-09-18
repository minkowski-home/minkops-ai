import { AGENTS, DEPARTMENTS } from "../content/agents";
import { FUNNEL_HREF, SITE } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { ButtonLink, Card, Eyebrow } from "../ui/primitives";

const FACTS = [
  { figure: "Under 10", label: "People on the team, most wearing four or five hats" },
  {
    figure: String(DEPARTMENTS.length),
    label: "Departments they cover, from the front desk to a building site"
  },
  {
    figure: String(AGENTS.length),
    label: "Roles designed, each one a job we needed ourselves"
  }
] as const;

const PRINCIPLES = [
  {
    title: "If we haven't used it, we won't sell it",
    body: "Every employee works inside our own businesses before it's offered to yours. Minkowski Home and Myndral are its first two customers, and by some distance the pickiest."
  },
  {
    title: "Quiet is the goal",
    body: "The best employee is the one you forget is there. We tune for fewer interruptions, not more impressive ones, and we measure ourselves by how little you have to think about us."
  },
  {
    title: "People above the line",
    body: "Our employees decide what they're allowed to decide. Everything else waits for a person, with the homework already done and a suggested answer attached."
  }
] as const;

const FAMILY = [
  {
    name: "Minkowski Home",
    href: SITE.links.minkowskiHome,
    body: "Interior product design, and the first business ever to run on Minkops."
  },
  {
    name: "Myndral",
    href: SITE.links.myndral,
    body: "A curated music label with its own musical universe. Its listener inbox runs through Imel."
  }
] as const;

export default function AboutPage() {
  return (
    <>
      <SeoHead
        title="About"
        description="Minkops is under ten people. We build the AI employees we sell, and run our own company on them first. Here's where it started and what we won't compromise on."
        path="/about"
      />

      <PageHero
        eyebrow="About"
        title="We run our own company on it first."
        lead="Minkops is under ten people, and most of us wear four or five hats before lunch. What makes that possible isn't hustle. We build the AI employees we're selling, then put them to work in our own businesses before anyone else gets them."
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
            Instead of hiring for every function at once, we built small AI helpers for
            specific jobs, from writing content to keeping the paperwork moving. They
            worked. They took on the repetitive thinking that would otherwise have meant
            another hire, and they did it the same way every time.
          </p>
          <p>
            So we gave them more. We spread them across departments, gave them a way to
            talk to each other, and shaped each one into a lasting role that matches a
            real job in a real business.
          </p>
          <p>
            That internal system became Minkops. Today the whole roster runs our own
            operations, from the inbox to the books, and every new role is built the same
            way: because we needed it before anyone else did.
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
        lead="Minkops sits alongside two very different businesses. That's useful: if the same employees can serve a furniture maker and a music label, the job underneath is the same."
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
              Four questions, about ninety seconds, and a straight answer about which
              employee we'd hire first for you.
            </p>
          </div>
          <div className="mk-cta-band__actions">
            <ButtonLink
              to={FUNNEL_HREF}
              size="lg"
              variant="primary"
              iconRight={<Icon name="chevronRight" size={16} />}
            >
              Find your first hire
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
