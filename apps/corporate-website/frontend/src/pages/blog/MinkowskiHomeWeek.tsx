import { POSTS } from "../../content/posts";
import { FUNNEL_HREF } from "../../content/site";
import BlogPostLayout, { PostNote } from "./BlogPostLayout";

export default function MinkowskiHomeWeek() {
  return (
    <BlogPostLayout
      post={POSTS.minkowskiHomeWeek}
      cta={{
        title: "Want to see this on your own inbox?",
        body: "Start with the one role that's costing you the most hours this month. Four questions will tell you which one that is.",
        label: "Find your first hire",
        to: FUNNEL_HREF
      }}
    >
      <p>
        Launches get the attention because they&apos;re dramatic. This story is
        deliberately less dramatic, because most of what actually costs a small business
        its time isn&apos;t the big launch. It&apos;s the ordinary Tuesday.
      </p>
      <p>
        <strong>Minkowski Home (MH)</strong> is a small furniture company. Before Minkops,
        a normal week meant someone (usually the same one or two people) triaging a shared
        inbox, answering the same handful of shipping and material questions over and
        over, and letting warm leads go cold because nobody got round to the follow-up.
        Here&apos;s what that same week looks like now.
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
