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
        <strong>Imel</strong>, who looks after our email, has been reading MH&apos;s inbox
        since before anyone opened a laptop. Order confirmations that never needed a
        person get filed on their own. A real question about a delayed shipment gets
        classified, checked against the actual logistics record, and drafted into a reply
        with the real delivery window, not a canned &quot;we&apos;ll look into it.&quot;
      </p>
      <PostNote label="What used to take a person 45–60 minutes a day">
        Reading every inbound email, deciding what&apos;s routine and what needs
        judgement, and drafting a reply that&apos;s actually specific to the
        customer&apos;s order. Now it&apos;s done before the workday starts.
      </PostNote>

      <h2>Wednesday. A question that would have sat for a day.</h2>
      <p>
        A customer writes in asking whether the walnut coffee table finish will match a
        chair they bought eight months ago. <strong>Kall</strong>, who runs our support
        desk, doesn&apos;t push this into a queue. It pulls the customer&apos;s order
        history, checks the finish batch notes, and answers directly, flagging a note for
        a person only because the answer touches a return-policy edge case outside its
        decision scope. That&apos;s the guardrail doing its job: Kall doesn&apos;t guess
        on the parts it isn&apos;t supposed to decide. It hands those over and keeps
        moving on everything else.
      </p>
      <PostNote label="The part that actually matters">
        It isn&apos;t that Kall answers fast. It&apos;s that it knows which questions
        it&apos;s allowed to answer on its own, and which ones it isn&apos;t.
      </PostNote>

      <h2>Friday. The leads that don&apos;t slip anymore.</h2>
      <p>
        MH used to lose a predictable share of warm leads to nothing more complicated than
        nobody following up in time. Now, when a prospect opens a quote three times but
        doesn&apos;t reply, that pattern gets flagged and worked. A follow-up goes out
        that mentions the specific pieces they were looking at, not a generic &quot;just
        checking in.&quot; It isn&apos;t a dramatic new capability. It&apos;s the
        unglamorous, repetitive discipline a growing business always means to keep up with
        and rarely does.
      </p>

      <h2>Why this is the case study that matters</h2>
      <p>
        Most weeks aren&apos;t launch weeks. Most weeks are inbox triage, the same three
        support questions, and a lead that almost got forgotten. That&apos;s where a small
        business really spends its hours, and it&apos;s exactly the part that doesn&apos;t
        need a person doing it by hand every week.
      </p>
      <p>
        MH still has people. They&apos;re just not the ones reading every email first
        anymore.
      </p>
    </BlogPostLayout>
  );
}
