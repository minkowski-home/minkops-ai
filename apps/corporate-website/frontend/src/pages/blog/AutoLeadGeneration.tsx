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
        body: "We're choosing a small group of early partners to shape this rep in real production environments. Tell us about yours.",
        label: "Request early access",
        to: ACCESS_HREF
      }}
    >
      <p>
        Lead generation is one of the last corners of modern business where we still
        accept an almost absurd amount of manual work. Teams spend hours stitching
        spreadsheets together, scraping websites, enriching contacts, verifying emails,
        writing outreach, tracking replies, booking meetings, updating a CRM and following
        up, only to repeat the whole cycle next week.
      </p>
      <p>
        At Minkops, we&apos;re starting to build a new kind of teammate: an{" "}
        <strong>AI sales rep</strong> that can own the entire top-of-funnel workflow from
        end to end. Not &quot;automation&quot; in the brittle sense of a chain of
        triggers, but a rep that can plan, reason, decide, act and improve, while staying
        inside strict guardrails.
      </p>
      <p>
        This post walks through what we&apos;re building, why we think it will change how
        businesses operate, and how we&apos;re approaching the hard parts: quality,
        compliance, personalisation and measurement.
      </p>

      <h2>Why lead generation is still broken</h2>
      <p>
        The core problem isn&apos;t a lack of tools. It&apos;s that the workflow is
        scattered across tools, channels and people, each with different incentives and
        incomplete context. The result is predictable:
      </p>
      <ul>
        <li>
          <strong>Inconsistent quality.</strong> Prospect lists drift away from the ideal
          customer profile (ICP), and outreach turns into a numbers game.
        </li>
        <li>
          <strong>Thin personalisation at scale.</strong> Even good teams can&apos;t
          deeply personalise hundreds of touches a week.
        </li>
        <li>
          <strong>Operational drag.</strong> Updating the CRM, de-duplicating contacts and
          managing sequences steals time from actually selling.
        </li>
        <li>
          <strong>Slow learning loops.</strong> When results are poor, it&apos;s hard to
          tell why: targeting, message-market fit, deliverability, timing or follow-up.
        </li>
      </ul>
      <p>
        An AI sales rep should fix this by keeping the whole workflow in one coherent
        loop:{" "}
        <strong>
          target, discover, validate, personalise, reach out, respond, route, learn
        </strong>
        .
      </p>

      <h2>What we mean by an AI sales rep</h2>
      <p>
        We&apos;re not building a spam bot. We&apos;re building an employee that behaves
        like a highly disciplined sales development rep: one that never forgets the
        playbook, never loses track of context and never stops iterating. Its real
        strength shows up when it works alongside the other employees on the team.
      </p>
      <PostNote label="Our north star">
        The rep should be able to start with a clear ICP and end with qualified meetings
        on a calendar, while keeping the brand voice, respecting compliance constraints
        and producing audit-ready reasoning for every action it takes.
      </PostNote>

      <h2>The workflow, from ICP to meetings</h2>
      <p>
        Here&apos;s the high-level pipeline we&apos;re implementing. Think of it as a
        living system that can be tuned, extended and audited.
      </p>

      <h3>1. Define the ICP as structured policy</h3>
      <p>
        Most teams describe an ICP loosely: &quot;mid-market SaaS&quot; or
        &quot;construction companies.&quot; Our rep needs something more precise, so we
        represent the ICP as structured constraints and preferences:
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
        Treating the ICP as policy matters because it makes the system testable. When the
        rep proposes a lead or a message, it can explain which constraints it satisfied
        and which signals it wasn&apos;t sure about.
      </p>

      <h3>2. Source candidates and build a lead graph</h3>
      <p>
        Instead of a flat spreadsheet, we think in graphs. A good lead isn&apos;t just a
        person. It&apos;s a <strong>relationship</strong> between a company, an intent
        signal, a role and a message angle.
      </p>
      <p>
        The rep gathers candidates from several sources (databases, websites, public
        signals, internal referrals, inbound hints) and builds a lead graph that includes:
      </p>
      <ul>
        <li>The company: domain, size, tech stack, category, hiring pace.</li>
        <li>The person: title, seniority, team, public writing, social presence.</li>
        <li>Signals: job posts, product launches, funding, tool adoption, intent.</li>
        <li>Message angles: pain points mapped to signals and product capabilities.</li>
      </ul>
      <p>
        This is where AI employees start to look different from point tools. The system
        isn&apos;t just collecting contacts. It&apos;s building a story about why this
        contact is a good fit <em>right now</em>.
      </p>

      <h3>3. Validate, enrich and protect deliverability</h3>
      <p>
        If you&apos;ve ever run outbound, you know deliverability is everything. A lead
        generation rep has to be opinionated about hygiene:
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
        Our rep personalises by choosing a <strong>reason to reach out</strong> (a
        signal), matching it to a <strong>message angle</strong> (a pain point), and
        making a <strong>single, credible ask</strong> (a next action).
      </p>
      <ul>
        <li>
          If a company is hiring SDRs, the angle might be speed to pipeline and consistent
          training.
        </li>
        <li>
          If a team recently adopted a tool we integrate with, the angle might be workflow
          automation and attribution.
        </li>
        <li>
          If a founder has written about outbound fatigue, the angle might be
          quality-first sequencing and deliverability.
        </li>
      </ul>
      <p>
        Crucially, the rep has to record its reasoning internally: which signal it used,
        what it couldn&apos;t verify, and what it chose <em>not</em> to claim. That cuts
        down on invented personalisation and keeps outreach honest.
      </p>

      <h3>5. Sequencing across channels that adapts to what happens</h3>
      <p>
        People don&apos;t follow a fixed cadence. A good SDR changes approach based on
        what happens, and the rep should do the same, within policy.
      </p>
      <p>
        Instead of a rigid &quot;day 1 email, day 3 email, day 5 LinkedIn&quot; sequence,
        we treat sequencing as a decision problem:
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
        Replies are where most automation falls apart. People ask messy questions about
        pricing, timing, competitors and edge cases. The rep needs a controlled ability to
        reason and respond. Our approach:
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
        This sounds mundane, but it&apos;s one of the biggest levers. If the rep owns the
        workflow, it should own the record of truth too:
      </p>
      <ul>
        <li>Create and update contacts and companies without duplicates.</li>
        <li>Log every touch and outcome: sent, bounced, replied, meeting booked.</li>
        <li>Record stage changes with reasons, not just a stage label.</li>
        <li>Attach the rationale: why this lead, why this message, why now.</li>
      </ul>
      <p>
        Done well, this means founders and teams can finally trust their pipeline data
        again, because one consistent system maintained it instead of many human habits.
      </p>

      <h2>Guardrails: compliance, consent and safety</h2>
      <p>
        Any system that sends outbound messages has to treat compliance and trust as
        first-class concerns. Our design includes:
      </p>
      <ul>
        <li>Rate limits, warm-up strategies and per-domain suppression.</li>
        <li>Automatic unsubscribe detection with immediate suppression.</li>
        <li>GDPR-aware handling for regions that require stricter processing.</li>
        <li>Audit logs for every decision and every message.</li>
        <li>Human approval gates for sensitive claims, pricing or unusual asks.</li>
      </ul>
      <p>
        We think of the rep as working under a strict company policy, because in the real
        world, that&apos;s how great teams grow without breaking trust.
      </p>

      <h2>Why this changes how a business works</h2>
      <p>
        When a lead generation workflow becomes an employee, the organisation changes. The
        bottleneck moves from &quot;how many touches can we do?&quot; to &quot;how good is
        our strategy and our offer?&quot; In practice, a smaller team can operate like a
        much larger one:
      </p>
      <ul>
        <li>Founders can launch new outbound experiments in hours, not weeks.</li>
        <li>RevOps can enforce hygiene automatically instead of chasing it.</li>
        <li>Sales can spend more time in qualified conversations and less on admin.</li>
        <li>
          Teams can iterate on messaging with real feedback loops and measurable outcomes.
        </li>
      </ul>
      <p>
        And perhaps most importantly, a business can stop treating lead generation as a
        chaotic art project and start treating it as a repeatable system that gets better
        over time.
      </p>

      <h2>Where we are today</h2>
      <p>
        We&apos;re early, and we&apos;re building deliberately. The first milestone is an
        rep that runs a narrow workflow reliably for our own use: a single ICP, a small
        set of channels, strict messaging boundaries and complete observability.
      </p>
      <p>
        From there we expand carefully: more industries, more channels, better intent
        signals, richer personalisation, smarter routing to people, and continuous
        evaluation.
      </p>
      <p>
        If you run a business where pipeline matters, we&apos;d love to talk. We&apos;re
        choosing a small group of early partners to help shape the rep in real production
        environments.
      </p>
    </BlogPostLayout>
  );
}
