import { SITE } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Icon } from "../ui/Icon";
import { Badge, ButtonLink, Card } from "../ui/primitives";

type Role = {
  title: string;
  team: string;
  location: string;
  pitch: string;
};

const ROLES: readonly Role[] = [
  {
    title: "Senior AI engineer",
    team: "Engineering",
    location: "Remote",
    pitch:
      "You'd work on the engine behind our AI employees: the rules that decide what each one may do alone, the moments it stops to ask a person, and the loop that turns every human correction into something it learns from."
  },
  {
    title: "Product designer",
    team: "Design",
    location: "Remote",
    pitch:
      "You'd shape the operator console, the place where one person meets a whole team. The job is making a queue of decisions feel calm, clear and quick to clear."
  },
  {
    title: "Growth manager",
    team: "Marketing",
    location: "Hybrid",
    pitch:
      "You'd tell the story of a company that runs on its own product, honestly, and find the first small businesses who want the same. No invented numbers, ever."
  }
];

function applyHref(role: Role) {
  const subject = encodeURIComponent(`Application: ${role.title}`);
  return `mailto:${SITE.emails.hr}?subject=${subject}`;
}

export default function CareersPage() {
  return (
    <>
      <SeoHead
        title="Careers"
        description="Small team, real responsibility, and colleagues who happen to be AI employees. Open roles in engineering, design and growth at Minkops."
        path="/careers"
      />

      <PageHero
        eyebrow="Careers"
        title="Work on the thing that takes on the work."
        lead="We're a small team with a lot of responsibility each, and some of our most reliable colleagues are the AI employees we build. If that sounds more interesting than strange, keep reading."
      />

      <Section eyebrow={`Open roles · ${ROLES.length}`} title="Where you'd fit.">
        <ul className="mk-roles">
          {ROLES.map((role) => (
            <li key={role.title}>
              <Card as="article" className="mk-role">
                <div className="mk-role__head">
                  <div className="mk-role__id">
                    <h3 className="mk-role__title">{role.title}</h3>
                    <p className="mk-role__meta">{role.location}</p>
                  </div>
                  <Badge>{role.team}</Badge>
                </div>
                <p className="mk-role__pitch">{role.pitch}</p>
                <ButtonLink
                  to={applyHref(role)}
                  variant="secondary"
                  size="md"
                  iconRight={<Icon name="chevronRight" size={14} />}
                  className="mk-role__apply"
                >
                  Apply for this role
                </ButtonLink>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section tone="sunken">
        <div className="mk-cta-band">
          <div className="mk-cta-band__text">
            <h2 className="mk-cta-band__title">Don't see your role?</h2>
            <p className="mk-cta-band__lead">
              Tell us what you'd do here anyway. Send your CV and a few lines to{" "}
              <a href={`mailto:${SITE.emails.hr}`}>{SITE.emails.hr}</a>. Business
              enquiries and collaborations go to{" "}
              <a href={`mailto:${SITE.emails.general}`}>{SITE.emails.general}</a>.
            </p>
          </div>
        </div>
      </Section>
    </>
  );
}
