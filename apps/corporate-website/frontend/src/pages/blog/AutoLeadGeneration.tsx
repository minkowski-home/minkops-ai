import { POSTS } from "../../content/posts";
import { ACCESS_HREF } from "../../content/site";
import BlogPostLayout, { PostCode, PostNote } from "./BlogPostLayout";

const ICP_POLICY = [
  "// Example: ICP policy snapshot (simplified)",
  "{",
  '  industry_allowlist: ["B2B SaaS", "DevTools"],',
  "  employee_count: >= 20 and <= 500,",
  '  geo_allowlist: ["US", "CA", "UK"],',
  '  buying_roles: ["Head of Sales", "RevOps", "Founder"],',
  '  disqualifiers: ["Student projects", "Agencies"],',
  '  tone: "concise, confident, technical when relevant"',
  "}"
] as const;

const SEQUENCING = [
  "// Pseudocode: policy-aware sequencing",
  'if lead.reply_intent == "positive": book_meeting()',
  'else if lead.reply_intent == "objection": route_to_human_or_handle()',
  "else if lead.deliverability_risk > 0.7: pause_and_reverify()",
  "else if lead.engaged_signal: follow_up_with_new_angle()",
  "else: continue_sequence_with_pacing()"
] as const;

export default function AutoLeadGeneration() {
  return (
    <BlogPostLayout
      post={POSTS.autoLeadGeneration}
      cta={{
        title: "Does pipeline keep you up at night?",
        body: "Tell us about a process you want to improve. We’ll discuss the required inputs, permissions and review points.",
        label: "Request early access",
        to: ACCESS_HREF
      }}
    >
      <PostNote label="Planning note">
        This is a design exploration, not a shipped outbound sales capability. No lead
        sourcing, email outreach, booking or CRM writes are verified by this article.
      </PostNote>
      <p>
        Lead generation is one of the last corners of modern business where we still
        accept an almost absurd amount of manual work. Teams spend hours stitching
        spreadsheets together, scraping websites, enriching contacts, verifying emails,
        writing outreach, tracking replies, booking meetings, updating a CRM and following
        up, only to repeat the whole cycle next week.
      </p>
      <p>
        This planning note explores how an AI Employee might be organized around a
        carefully scoped outbound Workflow. It describes questions to resolve before
        implementation; it does not report a product currently being built or available.
      </p>
      <p>
        The sections below outline possible inputs, permissions, review points and
        verification needs for such a design.
      </p>

      <h2>Why lead generation is still broken</h2>
      <p>
        A common design challenge is that lead work can be spread across tools, channels
        and people, with incomplete context. A workflow proposal should first identify
        which sources are authorized and which steps need a person:
      </p>
      <ul>
        <li>
          <strong>Data quality.</strong> How should prospect records be checked against an
          approved profile?
        </li>
        <li>
          <strong>Personalisation.</strong> Which verified signals may inform a draft?
        </li>
        <li>
          <strong>Record hygiene.</strong> Which CRM updates are allowed, and who reviews
          them?
        </li>
        <li>
          <strong>Evaluation.</strong> How will targeting, timing and follow-up outcomes be
          measured?
        </li>
      </ul>
      <p>
        A proposed Workflow could be scoped around a sequence such as:{" "}
        <strong>
          target, discover, validate, personalise, reach out, respond, route, learn
        </strong>
        .
      </p>

      <h2>What we mean by an AI sales rep</h2>
      <p>
        Here, &quot;AI sales rep&quot; is shorthand for a possible Employee grouping, not
        a claim about a shipped capability. Any Workflow would need a defined procedure,
        permitted tools and connectors, and explicit points for human review.
      </p>
      <PostNote label="Our north star">
        The rep should be able to start with a clear ICP and end with qualified meetings
        on a calendar, while keeping the brand voice, respecting compliance constraints
        and producing audit-ready reasoning for every action it takes.
      </PostNote>

      <h2>The workflow, from ICP to meetings</h2>
      <p>
        The outline below is one design to evaluate. Each step would need its own
        permissions, safeguards and success measures before implementation.
      </p>

      <h3>1. Define the ICP as structured policy</h3>
      <p>
        An ICP might be recorded as structured constraints and preferences instead of
        relying on an informal description:
      </p>
      <ul>
        <li>Company size ranges, revenue ranges and hiring signals.</li>
        <li>Technographics: tools used, integrations, platform choices.</li>
        <li>Geography, compliance restrictions and language requirements.</li>
        <li>Buying committee roles: who matters, who signs, who uses it.</li>
        <li>Disqualifiers: existing vendors, industries, red flags.</li>
      </ul>
      <PostCode label="Example ICP policy snapshot" lines={ICP_POLICY} />
      <p>
        A future implementation could make those constraints testable and show which
        approved signals support a proposed lead or draft, along with anything uncertain.
      </p>

      <h3>2. Source candidates and build a lead graph</h3>
      <p>
        A data model could connect a company, a verified intent signal, a role and a
        message angle instead of treating a lead as an isolated row.
      </p>
      <p>
        Before considering sources such as databases, websites, public signals, referrals
        or inbound enquiries, a deployment would need to document which sources are
        authorized. A proposed record could include:
      </p>
      <ul>
        <li>The company: domain, size, tech stack, category, hiring pace.</li>
        <li>The person: title, seniority, team, public writing, social presence.</li>
        <li>Signals: job posts, product launches, funding, tool adoption, intent.</li>
        <li>Message angles: pain points mapped to signals and product capabilities.</li>
      </ul>
      <p>
        Any fit assessment should show its supporting evidence and uncertainty for a
        person to review; this example does not source or enrich real leads.
      </p>

      <h3>3. Validate, enrich and protect deliverability</h3>
      <p>
        A design should define how it handles data hygiene:
      </p>
      <ul>
        <li>De-duplication across sources and sequences.</li>
        <li>Email verification and risk scoring for bounces and catch-all domains.</li>
        <li>Domain reputation checks and pacing control.</li>
        <li>Opt-out handling and suppression lists, both global and per account.</li>
      </ul>
      <PostNote label="A key principle">
        The rep should optimise for <em>long-term channel health</em>, not short-term
        volume. If deliverability degrades, everything else collapses with it.
      </PostNote>

      <h3>4. Write personalised outreach that doesn&apos;t sound fake</h3>
      <p>
        Personalisation has been flattened into shallow <code>Hey {"{{FirstName}}"}</code>{" "}
        tokens. Real personalisation shows you understand someone&apos;s situation and can
        suggest a sensible next step.
      </p>
      <p>
        A proposed draft could connect a <strong>reason to reach out</strong> (a
        verified signal), a <strong>message angle</strong> (an approved topic), and a
        <strong>single, reviewable ask</strong> (a next action).
      </p>
      <ul>
        <li>
          If a company is hiring SDRs, the angle might be speed to pipeline and consistent
          training.
        </li>
        <li>
          If a team uses a tool explicitly approved for a future workflow, an angle might
          discuss how the processes could fit together.
        </li>
        <li>
          If a founder has written about outbound fatigue, the angle might be
          quality-first sequencing and deliverability.
        </li>
      </ul>
      <p>
        Before any outreach capability exists, its design should record the source for
        each claim, what could not be verified, and what should not be stated.
      </p>

      <h3>5. Sequencing across channels that adapts to what happens</h3>
      <p>
        A Workflow should not assume a fixed cadence. Its policy could define when to
        stop, wait, change a draft or request human review.
      </p>
      <p>
        Instead of a rigid &quot;day 1 email, day 3 email, day 5 LinkedIn&quot; sequence,
        a design could treat sequencing as a decision problem:
      </p>
      <ul>
        <li>Which channel suits this persona best?</li>
        <li>What time window matches their likely schedule?</li>
        <li>Did we get a soft signal: a site visit, an open, a reply, a profile view?</li>
        <li>Should we stop, slow down, or bring in a person?</li>
      </ul>
      <PostCode label="Pseudocode for policy-aware sequencing" lines={SEQUENCING} />

      <h3>6. Handle replies like an employee, not a template</h3>
      <p>
        Replies can raise questions about pricing, timing, competitors or edge cases. A
        proposed reply Workflow would need clear boundaries:
      </p>
      <ul>
        <li>
          Sort replies by intent: positive, objection, neutral, unsubscribe, out of
          office.
        </li>
        <li>
          Answer from a constrained knowledge base: product facts, approved claims,
          pricing boundaries, case studies.
        </li>
        <li>Bring in a person when confidence is low or policy requires approval.</li>
        <li>Always reply in the same brand voice that started the conversation.</li>
      </ul>

      <h3>7. Keep the CRM up to date, and correct</h3>
      <p>
        If a future Workflow is permitted to update a CRM, its scope should specify:
      </p>
      <ul>
        <li>Create and update contacts and companies without duplicates.</li>
        <li>Log every touch and outcome: sent, bounced, replied, meeting booked.</li>
        <li>Record stage changes with reasons, not just a stage label.</li>
        <li>Attach the rationale: why this lead, why this message, why now.</li>
      </ul>
      <p>
        Any claimed improvement in record quality would need to be measured against a
        documented baseline.
      </p>

      <h2>Guardrails: compliance, consent and safety</h2>
      <p>
        A system that sends outbound messages would need to address compliance and trust
        before deployment. Design questions include:
      </p>
      <ul>
        <li>Rate limits, warm-up strategies and per-domain suppression.</li>
        <li>Automatic unsubscribe detection with immediate suppression.</li>
        <li>GDPR-aware handling for regions that require stricter processing.</li>
        <li>Audit logs for every decision and every message.</li>
        <li>Human approval gates for sensitive claims, pricing or unusual asks.</li>
      </ul>
      <p>
        These are requirements to evaluate, not safeguards this article claims are
        implemented.
      </p>

      <h2>Why this changes how a business works</h2>
      <p>
        If a scoped lead Workflow proves useful, it could change how a team spends time.
        A pilot could measure whether:
      </p>
      <ul>
        <li>Founders launch outbound experiments more quickly.</li>
        <li>RevOps improves record hygiene with less manual follow-up.</li>
        <li>Sales spends more time in qualified conversations and less on admin.</li>
        <li>
          Teams can iterate on messaging with real feedback loops and measurable outcomes.
        </li>
      </ul>
      <p>
        These are hypotheses, not promised results. A pilot would need agreed measures
        and a review of actual outcomes.
      </p>

      <h2>Where we are today</h2>
      <p>
        This article does not establish the current build or deployment status of an
        outbound product. A responsible first milestone, if approved, could scope one
        narrow process, one authorized source and explicit human review.
      </p>
      <p>
        Any expansion would depend on measured results, verified integrations, and
        separate decisions about industries, channels, data sources and permissions.
      </p>
      <p>
        If this kind of workflow is relevant to your business, contact Minkops to discuss
        the process and the evidence a real deployment would require.
      </p>
    </BlogPostLayout>
  );
}
