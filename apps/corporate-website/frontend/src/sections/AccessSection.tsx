import { ANCHORS } from "../content/site";
import { Section } from "../layout/Section";
import InterestForm from "./InterestForm";

const PROMISES = [
  {
    title: "We use it before we sell it",
    body: "We try these ideas in our own businesses to learn what helps and where a person should step in."
  },
  {
    title: "One employee, one whole role",
    body: "Choose an employee for a job you want off your plate, then decide what that job includes."
  },
  {
    title: "You stay in charge",
    body: "Agree on what it can do and when it should check with you. You can review what happened."
  },
  {
    title: "It doesn't clock off",
    body: "These examples are just illustrations. We first agree where the work fits and when it should ask you."
  }
] as const;

export default function AccessSection() {
  return (
    <Section
      id={ANCHORS.access}
      tone="sunken"
      eyebrow="Get access"
      title="Hire your first employee."
      lead="Tell us what you wish took less time. We’ll talk through what to hand off and where you want to stay involved."
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
