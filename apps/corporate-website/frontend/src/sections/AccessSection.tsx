import { ANCHORS } from "../content/site";
import { Section } from "../layout/Section";
import InterestForm from "./InterestForm";

const PROMISES = [
  {
    title: "We use it before we sell it",
    body: "We use our own businesses to learn where practical workflows help and where people need to review the result."
  },
  {
    title: "One employee, one whole role",
    body: "An Employee is a product grouping. Each Workflow defines a business outcome, its steps and the points where a person reviews or decides."
  },
  {
    title: "You stay in charge",
    body: "Approvals and decisions that need a person should be explicit in the Workflow, with a clear way to review what happened."
  },
  {
    title: "It doesn't clock off",
    body: "Examples on this site are illustrations. We confirm fit, integrations, permissions and verification before treating any Workflow as ready."
  }
] as const;

export default function AccessSection() {
  return (
    <Section
      id={ANCHORS.access}
      tone="sunken"
      eyebrow="Get access"
      title="Hire your first employee."
      lead="Tell us what the process should accomplish and where it happens today. We’ll discuss the steps, the tools you can authorize, and how you would verify the result."
    >
      <div className="mk-access">
        <ul className="mk-access__promises">
          {PROMISES.map((promise) => (
            <li key={promise.title} className="mk-access__promise">
              <h3 className="mk-access__promise-title">{promise.title}</h3>
              <p className="mk-access__promise-body">{promise.body}</p>
            </li>
          ))}
        </ul>
        <InterestForm />
      </div>
    </Section>
  );
}
