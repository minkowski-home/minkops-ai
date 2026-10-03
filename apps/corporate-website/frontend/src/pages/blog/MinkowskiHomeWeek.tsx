import { POSTS } from "../../content/posts";
import { FUNNEL_HREF } from "../../content/site";
import BlogPostLayout, { PostNote } from "./BlogPostLayout";

export default function MinkowskiHomeWeek() {
  return (
    <BlogPostLayout
      post={POSTS.minkowskiHomeWeek}
      cta={{
        title: "Want to see this on your own inbox?",
        body: "Describe a process you want to improve and see an illustrative workflow outline to discuss.",
        label: "Find a workflow starting point",
        to: FUNNEL_HREF
      }}
    >
      <PostNote label="Illustrative design example">
        This article sketches a possible Workflow. It is not evidence of a deployed
        Minkops integration, measured time savings or a verified customer result.
      </PostNote>
      <p>
        The example uses familiar furniture-business tasks to show how a Workflow could
        gather context, draft a response and route decisions that need a person.
      </p>
      <p>
        <strong>Minkowski Home (MH)</strong> is a small furniture company. These
        scenarios use it as context for a possible workflow; they do not describe the
        company&apos;s current systems or operations.
      </p>

      <h2>Monday, 7:14 a.m. The inbox is already handled.</h2>
      <p>
        In this proposed scenario, an inbox Workflow sorts routine confirmations and
        prepares a reply to a shipping question using an authorized logistics record. It
        pauses for review when the source data or policy does not support a safe answer.
        This page does not connect to an inbox or logistics system.
      </p>
      <PostNote label="Scope of this example">
        The sketch shows possible classification, context gathering and draft preparation.
        It makes no estimate of time saved and does not claim a message was sent.
      </PostNote>

      <h2>Wednesday. A question that would have sat for a day.</h2>
      <p>
        A sample question asks whether a walnut finish will match a prior purchase. A
        possible Workflow would gather only authorized order and product context, draft a
        response, and ask a person to review any return-policy edge case. These are
        proposed steps, not actions performed for a customer.
      </p>
      <PostNote label="The review boundary">
        A real deployment would need defined permissions and escalation rules before it
        could answer or change anything in a customer record.
      </PostNote>

      <h2>Friday. The leads that don&apos;t slip anymore.</h2>
      <p>
        A separate example starts with an enquiry that has not received a follow-up. A
        proposed Workflow could prepare a reminder from approved quote details for a
        person to review. It does not monitor quote activity or send outreach today.
      </p>

      <h2>Why this is the case study that matters</h2>
      <p>
        These examples focus on repeatable work: classifying a request, gathering
        approved context, preparing a draft and routing exceptions. They illustrate a
        design discussion; they do not establish Minkowski Home&apos;s current workload,
        product deployment or customer outcomes.
      </p>
      <p>
        People remain responsible for the review points and decisions defined for any
        Workflow that might be deployed.
      </p>
    </BlogPostLayout>
  );
}
