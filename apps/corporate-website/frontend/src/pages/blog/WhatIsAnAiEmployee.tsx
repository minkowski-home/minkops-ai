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
        body: "Describe a process you want to improve and see an illustrative workflow outline to discuss.",
        label: "Find a workflow starting point",
        to: FUNNEL_HREF
      }}
    >
      <p>
        This guide explains the terms used by Minkops. “AI Employee” describes a product
        grouping; a Workflow defines the business outcome and steps. It does not mean a
        particular system is connected or ready to act.
      </p>
      <p>
        Skills describe procedures. Tools and connectors provide approved access to
        systems. People remain responsible for granting that access and reviewing
        outcomes where judgment is needed.
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
        An <strong>AI Employee</strong> is Minkops&apos; product grouping. A{" "}
        <strong>Workflow</strong> defines the outcome, the procedure, the approved tools
        and connectors it may use, and where a person reviews or decides. The actual
        integrations and permissions must be confirmed for each deployment.
      </p>
      <p>
        So ask <strong>what is connected and verified?</strong> A demonstration, a
        written procedure and a live external action are different things. Confirm which
        tools are authorized, which actions require approval, and how the result can be
        checked.
      </p>

      <h2>What an AI employee needs to do a real job</h2>
      <p>
        This is where most &quot;AI agent&quot; products quietly fall short. The four
        things below are genuinely hard to build, and easy to fake in a demo.
      </p>
      <ul>
        <li>
          <strong>Relevant context.</strong> Identify which approved business information
          the Workflow needs, how it is accessed and how it stays current.
        </li>
        <li>
          <strong>A defined scope.</strong> Document what the Workflow may do, what tools
          it can access, and which actions require sign-off.
        </li>
        <li>
          <strong>A review path.</strong> Define where the Workflow pauses for an
          approval, escalation or decision that needs a person.
        </li>
        <li>
          <strong>Verification.</strong> Specify how someone can confirm an external
          action succeeded, such as a sent reply or an updated record.
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
        In Minkops&apos; model, an Employee is the product grouping and a{" "}
        <strong>Workflow</strong> describes the outcome and steps. The{" "}
        <Link to="/orchestration">product model</Link> also names the procedural skills
        and approved tools or connectors involved. Specific access and external writes
        must be verified for each deployment.
      </p>
      <p>
        Those details make the difference between a useful design description and a
        verified workflow running against real systems.
      </p>
    </BlogPostLayout>
  );
}
