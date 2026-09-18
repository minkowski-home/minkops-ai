import { Link } from "react-router-dom";
import { POSTS } from "../../content/posts";
import { FUNNEL_HREF } from "../../content/site";
import BlogPostLayout from "./BlogPostLayout";

export default function WhatIsAnAiEmployee() {
  return (
    <BlogPostLayout
      post={POSTS.whatIsAnAiEmployee}
      cta={{
        title: "Not sure which role to hire first?",
        body: "Answer four questions and get a specific recommendation in about ninety seconds. No call, no demo booking.",
        label: "Find your first hire",
        to: FUNNEL_HREF
      }}
    >
      <p>
        Every second software product now calls itself &quot;AI-powered.&quot; Somewhere
        in that noise, a genuinely different category has appeared, and most buyers
        haven&apos;t been given the words to tell it apart: the{" "}
        <strong>AI employee</strong>.
      </p>
      <p>
        If you run a small business and you&apos;re trying to work out whether a given AI
        product deserves your time, this is the most useful distinction to understand
        before you look at anything else.
      </p>

      <h2>You operate a tool. You hire an employee.</h2>
      <p>
        An <strong>AI tool</strong> (a writing assistant, a chatbot widget, a summariser
        bolted onto your inbox) still needs a person in the loop for every unit of work.
        You open it, you give it a prompt or a document, it gives you an output, and then{" "}
        <em>you</em> do the actual job. You send the email. You update the record. You
        decide what happens next.
      </p>
      <p>
        An <strong>AI employee</strong> is given a role, not a prompt box. It has standing
        access to the context it needs for that job: your inbox, your ticket queue, your
        customer records, your product catalog. It carries the work through to the end
        inside guardrails you set, the same way you&apos;d hand a role to a new hire and
        trust them to run with it once they&apos;re trained.
      </p>
      <p>
        So the test isn&apos;t &quot;does it use AI.&quot; Almost everything does now. The
        test is <strong>who does the last step?</strong> If a person still has to take the
        output and turn it into the action (the sent reply, the resolved ticket, the
        updated record), you&apos;re looking at a tool. If the system takes that last step
        itself, inside limits it can&apos;t override, you&apos;re looking at something
        much closer to an employee.
      </p>

      <h2>What an AI employee needs to do a real job</h2>
      <p>
        This is where most &quot;AI agent&quot; products quietly fall short. The four
        things below are genuinely hard to build, and easy to fake in a demo.
      </p>
      <ul>
        <li>
          <strong>Shared context, not a blank slate.</strong> A real employee doesn&apos;t
          re-learn your business every morning. An AI employee needs standing access to
          company knowledge (policies, product facts, customer history) so it isn&apos;t
          starting from zero on every conversation.
        </li>
        <li>
          <strong>A defined scope, not open-ended autonomy.</strong> &quot;Do whatever
          seems right&quot; isn&apos;t a job description, for a person or an AI employee.
          A well-built AI employee works inside an explicit policy: what it may decide on
          its own, and what needs sign-off.
        </li>
        <li>
          <strong>A real way to ask for help.</strong> The honest failure mode for an AI
          employee isn&apos;t &quot;it made a mistake.&quot; Every new hire does that.
          It&apos;s &quot;it wasn&apos;t sure, and it guessed instead of asking.&quot; The
          systems worth trusting are built to stop and ask a person when confidence is
          low, not tuned to always sound confident.
        </li>
        <li>
          <strong>Memory that lasts.</strong> If it forgets the customer it spoke to
          yesterday, it isn&apos;t working like an employee. It&apos;s working like a
          form.
        </li>
      </ul>

      <h2>How to size one up in five minutes</h2>
      <p>
        Ask the vendor these directly. The answers will tell you more than any feature
        list.
      </p>
      <ul>
        <li>
          When it finishes, does a person still have to act on the output, or is the
          action already done?
        </li>
        <li>
          What happens when it doesn&apos;t know the answer? Does it ask, or improvise?
        </li>
        <li>
          Does it remember the last time it dealt with this particular customer or record?
        </li>
        <li>
          Is it one narrow bot per task, or one role covering the ground a single hire
          would cover?
        </li>
      </ul>

      <h2>What this looks like in practice</h2>
      <p>
        At Minkops, this distinction is the whole design brief. <strong>Imel</strong>, who
        looks after email, doesn&apos;t hand you a draft to review and send yourself. It
        reads the incoming message, checks it against your policies, and drafts (or sends,
        depending on the guardrails you set) the reply. <strong>Kall</strong>, who runs
        support, doesn&apos;t summarise a ticket for someone else to close. It resolves
        the ticket and updates the record itself. Everyone on the roster shares the same{" "}
        <Link to="/orchestration">way of working</Link>, so adding a role doesn&apos;t
        mean bolting on another disconnected bot. It means hiring into the same team.
      </p>
      <p>
        That&apos;s the real bar an AI employee has to clear. Plenty of tools can hold a
        conversation now. The question is whether you can hand it a role and trust it to
        do the job.
      </p>
    </BlogPostLayout>
  );
}
