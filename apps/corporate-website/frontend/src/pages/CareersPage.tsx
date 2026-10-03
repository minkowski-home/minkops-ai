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
      "You'd work on how a Workflow represents its steps, the approved tools it can use, and the moments it must stop for human review."
  },
  {
    title: "Product designer",
    team: "Design",
    location: "Remote",
    pitch:
      "You'd shape how people define, review and verify a Workflow's outcomes when it uses approved tools and connectors."
  },
  {
    title: "Growth manager",
    team: "Marketing",
    location: "Hybrid",
    pitch:
      "You'd explain the Employee and Workflow model clearly and help businesses assess fit without implying unverified integrations or results."
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
        description="Work on the system that organizes AI Employees around business Workflows, with explicit tools and human review."
        path="/careers"
      />

      <PageHero
        eyebrow="Careers"
        title="Work on the thing that takes on the work."
        lead="We're building a product that organizes AI Employees around defined business Workflows. Our engineering, design and growth work connects clear procedures, approved system access and review by people."
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
