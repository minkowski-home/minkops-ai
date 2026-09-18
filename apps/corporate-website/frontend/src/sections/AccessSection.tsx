import type { WorkArea } from "../content/funnel";
import type { Team } from "../content/team";
import { ANCHORS } from "../content/site";
import { Section } from "../layout/Section";
import InterestForm from "./InterestForm";

const PROMISES = [
  {
    title: "We use it before we sell it",
    body: "Imel reads our own inbox and drafts replies before anyone on the team opens it. Kall works our support queue. If something is rough, we're the first to feel it."
  },
  {
    title: "One employee, one whole role",
    body: "Each one takes an entire job with its own skills, not a single chore. They talk to each other and share one memory of your business, so nothing gets explained twice."
  },
  {
    title: "You stay in charge",
    body: "Anything above an employee's authority lands in your queue with a drafted answer. You approve it, change it, or take it from there, and every correction teaches them something."
  },
  {
    title: "It doesn't clock off",
    body: "Your team works around the clock, not in one-off bursts. Monday morning starts with the weekend already handled."
  }
] as const;

export default function AccessSection({
  suggestedArea,
  team
}: {
  suggestedArea?: WorkArea;
  team: Team;
}) {
  return (
    <Section
      id={ANCHORS.access}
      tone="sunken"
      eyebrow="Get access"
      title="Hire your first employee."
      lead="Minkops is pre-sale, and that's on purpose. Our first customers get their team set up by hand, by the people who built it, so we can see what works in your business and not just in ours."
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
        <InterestForm suggestedArea={suggestedArea} team={team} />
      </div>
    </Section>
  );
}
