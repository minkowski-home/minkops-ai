import type { ReactNode } from "react";
import { SITE } from "../content/site";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";

/*
 * Terms of service and privacy policy.
 *
 * The clause text below is legal copy and is reproduced word for word from
 * the previous site. Only the page intro and presentation are ours to change;
 * edits to the clauses themselves need legal review.
 */

type Clause = { heading: string; body: ReactNode };

const Email = ({ address }: { address: string }) => (
  <a href={`mailto:${address}`}>{address}</a>
);

function LegalPage({
  title,
  lead,
  path,
  description,
  clauses
}: {
  title: string;
  lead: ReactNode;
  path: string;
  description: string;
  clauses: readonly Clause[];
}) {
  return (
    <>
      <SeoHead title={title} description={description} path={path} />
      <PageHero eyebrow="Legal" title={title} lead={lead} />
      <Section narrow>
        <ol className="mk-legal">
          {clauses.map((clause, index) => (
            <li key={clause.heading} className="mk-legal__clause">
              <span className="mk-legal__number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="mk-legal__text">
                <h2 className="mk-legal__heading">{clause.heading}</h2>
                <p>{clause.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}

const CORPORATE_ADDRESS =
  "Minkops is a product of Minkowski Home. Our corporate mailing address is 375 University Avenue Suite 3215, Toronto, ON M5G 2J5, Canada.";

export function TermsOfServicePage() {
  return (
    <LegalPage
      title="Terms of service"
      path="/terms"
      description="The terms that apply when you use Minkops, a product of Minkowski Home."
      lead={
        <>
          The agreement between you and us, in five short clauses. If anything here is
          unclear, write to <Email address={SITE.emails.general} /> and a person will walk
          you through it.
        </>
      }
      clauses={[
        {
          heading: "Acceptance of Terms",
          body: "By accessing and using Minkops, a product of Minkowski Home, you accept and agree to be bound by the terms and provision of this agreement."
        },
        {
          heading: "Use of Service",
          body: "Our AI agents are designed to assist with business operations. You agree to use these agents responsibly and in compliance with all applicable laws and regulations."
        },
        {
          heading: "Data & Privacy",
          body: "We respect your data. Your interaction with our agents is encrypted and governed by our Privacy Policy."
        },
        {
          heading: "Contact Information",
          body: (
            <>
              For business enquiries and collaborations, contact{" "}
              <Email address={SITE.emails.general} />. For HR matters, employee
              verification, and job applications, contact{" "}
              <Email address={SITE.emails.hr} />.
            </>
          )
        },
        { heading: "Corporate Address", body: CORPORATE_ADDRESS }
      ]}
    />
  );
}

export function PrivacyPolicyPage() {
  return (
    <LegalPage
      title="Privacy policy"
      path="/privacy"
      description="What Minkops collects when you get in touch, what we use it for, and how to reach us about it."
      lead={
        <>
          What we collect when you talk to us, and what we do with it. Questions about
          your data go to <Email address={SITE.emails.general} />, and a person answers
          them.
        </>
      }
      clauses={[
        {
          heading: "Information Collection",
          body: "We collect information that you provide directly to us when you request access, create an account, or communicate with us."
        },
        {
          heading: "Use of Information",
          body: "We use the information we collect to provide, maintain, and improve our services, including our AI agents."
        },
        {
          heading: "Data Security",
          body: "We implement appropriate security measures to protect your personal information against unauthorized access or disclosure."
        },
        {
          heading: "Contact Us",
          body: (
            <>
              If you have questions about this Privacy Policy or business collaborations,
              contact <Email address={SITE.emails.general} />. For HR-related requests,
              employee verification, and job applications, contact{" "}
              <Email address={SITE.emails.hr} />.
            </>
          )
        },
        { heading: "Corporate Address", body: CORPORATE_ADDRESS }
      ]}
    />
  );
}
